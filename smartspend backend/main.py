from datetime import date
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
import services
import llm_coach
import ingestion
from database import engine, get_db, Base
from utils import normalize_category

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SmartSpend AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Users ----------

@app.post("/users", response_model=schemas.UserOut)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = models.User(name=user.name, monthly_income=user.monthly_income)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


# ---------- Budgets ----------

@app.post("/budgets", response_model=schemas.BudgetOut)
def create_budget(budget: schemas.BudgetCreate, db: Session = Depends(get_db)):
    category = normalize_category(budget.category)

    existing = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == budget.user_id,
            models.Budget.category == category,
            models.Budget.month == budget.month,
            models.Budget.year == budget.year,
        )
        .first()
    )
    if existing:
        # Budget already exists for this category/month -> update limit instead of duplicating
        existing.monthly_limit = budget.monthly_limit
        db.commit()
        db.refresh(existing)
        return existing

    db_budget = models.Budget(
        user_id=budget.user_id,
        category=category,
        monthly_limit=budget.monthly_limit,
        month=budget.month,
        year=budget.year,
    )
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget


@app.get("/budgets/{user_id}", response_model=list[schemas.BudgetOut])
def list_budgets(user_id: int, year: int, month: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user_id, models.Budget.year == year, models.Budget.month == month)
        .all()
    )


# ---------- Transactions ----------

@app.post("/transactions", response_model=schemas.TransactionOut)
def create_transaction(txn: schemas.TransactionCreate, db: Session = Depends(get_db)):
    data = txn.model_dump()
    data["category"] = services.resolve_transaction_category(
        db, txn.user_id, txn.category, txn.date.year, txn.date.month
    )
    db_txn = models.Transaction(**data)
    db.add(db_txn)
    db.commit()
    db.refresh(db_txn)
    return db_txn


@app.get("/transactions/{user_id}", response_model=list[schemas.TransactionOut])
def list_transactions(user_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == user_id)
        .order_by(models.Transaction.date.desc())
        .all()
    )


@app.delete("/transactions/item/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    db_txn = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not db_txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(db_txn)
    db.commit()
    return {"deleted": True, "id": transaction_id}


# ---------- Pace tracking / burn rate ----------

@app.get("/pace/{user_id}/{category}", response_model=schemas.PaceStatus)
def get_pace(user_id: int, category: str, year: int, month: int, db: Session = Depends(get_db)):
    result = services.calculate_pace(db, user_id, category, year, month)
    if result is None:
        raise HTTPException(status_code=404, detail="No budget set for this category/month")
    return result


@app.get("/pace/{user_id}", response_model=list[schemas.PaceStatus])
def get_pace_all_categories(user_id: int, year: int, month: int, db: Session = Depends(get_db)):
    budgets = (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user_id, models.Budget.year == year, models.Budget.month == month)
        .all()
    )
    results = []
    for b in budgets:
        r = services.calculate_pace(db, user_id, b.category, year, month)
        if r:
            results.append(r)
    return results


# ---------- "Should I Buy This?" ----------

@app.post("/buy-decision", response_model=schemas.BuyDecisionResponse)
def buy_decision(req: schemas.BuyDecisionRequest, db: Session = Depends(get_db)):
    today = date.today()
    return services.evaluate_purchase(db, req.user_id, req.category, req.item_cost, today.year, today.month)


# ---------- AI Financial Coach ----------

@app.get("/coach/{user_id}", response_model=schemas.CoachResponse)
def get_coaching(user_id: int, year: int = None, month: int = None, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    budgets = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user_id,
            models.Budget.year == target_year,
            models.Budget.month == target_month,
        )
        .all()
    )
    pace_data = []
    for b in budgets:
        r = services.calculate_pace(db, user_id, b.category, target_year, target_month)
        if r:
            pace_data.append(r)

    try:
        advice = llm_coach.get_coaching_advice(user.name, user.monthly_income, pace_data)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

    return {"advice": advice}


# ---------- Smart Anomaly Detection ----------

@app.get("/anomalies/{user_id}", response_model=list[schemas.AnomalyItem])
def get_anomalies(user_id: int, year: int, month: int, db: Session = Depends(get_db)):
    return services.get_anomalies(db, user_id, year, month)


# ---------- Automated Ingestion ----------

@app.post("/ingest/sms", response_model=list[schemas.ParsedTransactionPreview])
def ingest_sms(req: schemas.SmsIngestRequest):
    """Parses pasted bank SMS text (one message per line) into a preview list.
    Does NOT save anything — call /ingest/commit to actually insert."""
    parsed = ingestion.parse_sms_text(req.raw_text)
    if not parsed:
        raise HTTPException(
            status_code=422,
            detail="No debit transactions could be parsed from that text. "
            "Make sure each SMS is on its own line and mentions an amount (Rs./INR).",
        )
    return parsed


@app.post("/ingest/statement", response_model=list[schemas.ParsedTransactionPreview])
async def ingest_statement(file: UploadFile = File(...)):
    """Parses an uploaded bank statement (CSV or PDF) into a preview list.
    Does NOT save anything — call /ingest/commit to actually insert."""
    content = await file.read()
    filename = (file.filename or "").lower()

    try:
        if filename.endswith(".csv"):
            parsed = ingestion.parse_csv_statement(content)
        elif filename.endswith(".pdf"):
            parsed = ingestion.parse_pdf_statement(content)
        else:
            raise HTTPException(status_code=400, detail="Only .csv and .pdf files are supported.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse this file: {e}")

    if not parsed:
        raise HTTPException(
            status_code=422,
            detail="No debit transactions could be identified in this statement. "
            "Check that it has date, description, and debit/withdrawal columns.",
        )
    return parsed


@app.post("/ingest/commit", response_model=schemas.CommitIngestResponse)
def commit_ingest(req: schemas.CommitIngestRequest, db: Session = Depends(get_db)):
    """Inserts a reviewed/edited batch of parsed transactions."""
    count = 0
    for t in req.transactions:
        resolved_category = services.resolve_transaction_category(
            db, req.user_id, t.category, t.date.year, t.date.month
        )
        db_txn = models.Transaction(
            user_id=req.user_id,
            amount=t.amount,
            category=resolved_category,
            date=t.date,
            note=t.note,
            merchant=t.merchant,
            source=t.source,
            frequency=t.frequency,
        )
        db.add(db_txn)
        count += 1
    db.commit()
    return {"inserted": count}


# ---------- Monthly Bills ----------

@app.post("/bills")
def create_bill(bill: schemas.BillCreate, db: Session = Depends(get_db)):
    db_bill = models.Bill(
        user_id=bill.user_id,
        name=bill.name.strip(),
        category=normalize_category(bill.category),
        amount=bill.amount,
        due_day=bill.due_day,
    )
    db.add(db_bill)
    db.commit()
    db.refresh(db_bill)

    # Give it its own row on the dashboard immediately, even before it's paid.
    today = date.today()
    services.ensure_category_budget(
        db, bill.user_id, bill.category,
        bill.year or today.year, bill.month or today.month,
        default_limit=bill.amount,
    )

    return {"id": db_bill.id, "name": db_bill.name, "category": db_bill.category,
            "amount": db_bill.amount, "due_day": db_bill.due_day}


@app.get("/bills/{user_id}", response_model=list[schemas.BillStatus])
def list_bills(user_id: int, year: int, month: int, db: Session = Depends(get_db)):
    return services.get_bills_with_status(db, user_id, year, month)


@app.post("/bills/{bill_id}/pay", response_model=schemas.BillStatus)
def pay_bill(bill_id: int, year: int, month: int, db: Session = Depends(get_db)):
    payment = services.mark_bill_paid(db, bill_id, year, month)
    if payment is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill = db.query(models.Bill).filter(models.Bill.id == bill_id).first()
    return {
        "id": bill.id, "name": bill.name, "category": bill.category,
        "amount": bill.amount, "due_day": bill.due_day,
        "status": "paid", "paid_date": payment.paid_date,
    }


@app.post("/bills/{bill_id}/unpay", response_model=schemas.BillStatus)
def unpay_bill(bill_id: int, year: int, month: int, db: Session = Depends(get_db)):
    services.mark_bill_unpaid(db, bill_id, year, month)
    bill = db.query(models.Bill).filter(models.Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    today = date.today()
    status = "overdue" if (today.year == year and today.month == month and today.day > bill.due_day) else "due"
    return {
        "id": bill.id, "name": bill.name, "category": bill.category,
        "amount": bill.amount, "due_day": bill.due_day,
        "status": status, "paid_date": None,
    }


@app.delete("/bills/{bill_id}")
def delete_bill(bill_id: int, db: Session = Depends(get_db)):
    bill = db.query(models.Bill).filter(models.Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    db.delete(bill)
    db.commit()
    return {"deleted": True, "id": bill_id}


@app.get("/")
def root():
    return {"status": "SmartSpend AI backend running"}
