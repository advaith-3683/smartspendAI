import json
import uuid
import os
import time
from startup_telemetry import startup_stage
print(json.dumps({'event': 'startup_stage', 'stage': 'application_import', 'status': 'started'}), flush=True)
_import_started = time.monotonic()
from datetime import date
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from threading import Lock
from contextlib import asynccontextmanager
import auth
from migrations import migrate
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
import services
import llm_coach
import ingestion
from database import engine, get_db, Base
from utils import normalize_category

ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
if "*" in ORIGINS:
    raise RuntimeError("CORS_ORIGINS must contain exact origins")

@asynccontextmanager
async def lifespan(app):
    global DUMMY_HASH
    try:
        with startup_stage('database_security'):
            if engine.dialect.name == 'postgresql':
                from postgres_storage import verify_postgres
                verify_postgres(engine, Base.metadata)
            else:
                migrate(engine, Base.metadata)
        with startup_stage('authentication'):
            DUMMY_HASH = auth.password_hash('dummy-password-not-used')
    except Exception as error:
        from database_diagnostics import diagnostic_json
        print(diagnostic_json(error, 'security_verification'), flush=True)
        raise RuntimeError('Required startup check failed; see sanitized diagnostics.') from None
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="SmartSpend AI", lifespan=lifespan)




DUMMY_HASH = None  # Initialized by required lifespan startup before requests.
_rate_lock = Lock()
_rate_buckets = {}


@app.middleware("http")
async def request_limits(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in ORIGINS:
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    # Bound actual streamed bytes as well as the declared Content-Length.
    size = 0
    original_receive = request._receive
    async def bounded_receive():
        nonlocal size
        message = await original_receive()
        size += len(message.get("body", b""))
        if size > 6 * 1024 * 1024:
            raise HTTPException(413, "Request exceeds 6 MiB")
        return message
    request._receive = bounded_receive
    path = request.url.path
    group, limit = ("auth", 10) if path.startswith("/auth/") and path != "/auth/me" else (("expensive", 10) if (any(x in path for x in ("/coach", "/ingest", "/savings-goal")) and not path.startswith("/coach/proposals/")) else ("general", 180))
    # Token-derived key after authentication is handled by expiry; IP additionally
    # bounds anonymous work. Do not trust forwarded headers from arbitrary clients.
    key = (request.client.host if request.client else "unknown", group)
    now = time.monotonic()
    with _rate_lock:
        for stale in [k for k, v in _rate_buckets.items() if now - v[0] >= 60]:
            del _rate_buckets[stale]
        start, count = _rate_buckets.get(key, (now, 0))
        if count >= limit:
            return JSONResponse({"detail": "Rate limit exceeded; retry in a minute"}, status_code=429, headers={"Retry-After": "60"})
        _rate_buckets[key] = (start, count + 1)
    try:
        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


# ---------- Users ----------

class Signup(auth.Login, schemas.UserCreate):
    monthly_income: schemas.Decimal = schemas.Decimal("0")
    model_config = {"str_strip_whitespace": False}

    @schemas.field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


@app.post("/auth/signup", response_model=schemas.UserOut)
def signup(req: Signup, response: Response, db: Session = Depends(get_db)):
    user = models.User(name=req.name, monthly_income=req.monthly_income)
    db.add(user)
    db.flush()
    db.add(auth.EmailAccount(user_id=user.id, email=req.email, password_hash=auth.password_hash(req.password)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email unavailable")
    auth.issue_session(db, response, user.id)
    return user


@app.post("/auth/login", response_model=schemas.UserOut)
def login(req: auth.Login | auth.LegacyLogin, response: Response, db: Session = Depends(get_db)):
    if isinstance(req, auth.LegacyLogin):
        credential = db.query(auth.Credential).filter_by(username=req.username.lower()).first()
        if credential and db.get(auth.EmailAccount, credential.user_id):
            credential = None
    else:
        credential = db.query(auth.EmailAccount).filter_by(email=req.email).first()
    # Perform the same expensive hash when the username does not exist.
    stored = credential.password_hash if credential else DUMMY_HASH
    if not auth.password_matches(req.password, stored) or not credential:
        raise HTTPException(401, "Invalid sign-in details")
    auth.issue_session(db, response, credential.user_id)
    return db.get(models.User, credential.user_id)


@app.post("/auth/legacy-login", response_model=schemas.UserOut)
def legacy_login(req: auth.LegacyLogin, response: Response, db: Session = Depends(get_db)):
    return login(req, response, db)


@app.post("/auth/enroll-email", response_model=schemas.UserOut)
def enroll_email(req: auth.EmailEnrollment, user=Depends(auth.current_user), db: Session = Depends(get_db)):
    legacy = db.get(auth.Credential, user.id)
    stored = legacy.password_hash if legacy else DUMMY_HASH
    if not auth.password_matches(req.current_password, stored) or not legacy:
        raise HTTPException(403, "Invalid sign-in details")
    if db.get(auth.EmailAccount, user.id):
        raise HTTPException(409, "This account already has an email")
    db.add(auth.EmailAccount(user_id=user.id, email=req.email, password_hash=legacy.password_hash))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email unavailable")
    db.expire(user, ["email_account"])
    return user


@app.get("/auth/me", response_model=schemas.UserOut)
def me(user=Depends(auth.current_user)):
    return user


@app.patch("/auth/me", response_model=schemas.UserOut)
def update_profile(req: schemas.UserCreate, user=Depends(auth.current_user), db: Session = Depends(get_db)):
    user.name = req.name
    user.monthly_income = req.monthly_income
    db.commit()
    return user


@app.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(auth.COOKIE)
    if token:
        db.query(auth.AuthSession).filter_by(token_hash=auth.token_hash(token)).delete()
        db.commit()
    response.delete_cookie(auth.COOKIE, path="/", secure=auth.SECURE, samesite=auth.SAMESITE)
    return {"logged_out": True}


@app.get("/users/{user_id}", response_model=schemas.UserOut, dependencies=[Depends(auth.authorize)])
def get_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


# ---------- Budgets ----------

@app.post("/budgets", response_model=schemas.BudgetOut, dependencies=[Depends(auth.authorize)])
def create_budget(budget: schemas.BudgetCreate, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    budget.user_id = user.id
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

    if db.query(models.Budget).filter_by(user_id=budget.user_id, year=budget.year, month=budget.month).count() >= 100:
        raise HTTPException(422, "At most 100 budget categories per month")
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


@app.get("/budgets/{user_id}", response_model=list[schemas.BudgetOut], dependencies=[Depends(auth.authorize)])
def list_budgets(user_id: int, year: int, month: int, db: Session = Depends(get_db)):
    return (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user_id, models.Budget.year == year, models.Budget.month == month)
        .all()
    )


# ---------- Transactions ----------

@app.post("/transactions", response_model=schemas.TransactionOut, dependencies=[Depends(auth.authorize)])
def create_transaction(txn: schemas.TransactionCreate, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    txn.user_id = user.id
    data = txn.model_dump()
    data["category"] = services.resolve_transaction_category(
        db, txn.user_id, txn.category, txn.date.year, txn.date.month
    )
    db_txn = models.Transaction(**data)
    db.add(db_txn)
    db.commit()
    db.refresh(db_txn)
    return db_txn


@app.get("/transactions/{user_id}", response_model=list[schemas.TransactionOut], dependencies=[Depends(auth.authorize)])
def list_transactions(user_id: int, year: int | None = None, month: int | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Transaction).filter(models.Transaction.user_id == user_id)
    if year is not None and month is not None:
        start = date(year, month, 1)
        end = date(year, month, services.get_days_in_month(year, month))
        query = query.filter(models.Transaction.date >= start, models.Transaction.date <= end)
    return query.order_by(models.Transaction.date.desc()).all()


@app.delete("/transactions/item/{transaction_id}", dependencies=[Depends(auth.authorize)])
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    db_txn = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not db_txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.query(models.BillPayment).filter(models.BillPayment.transaction_id == transaction_id).update({"paid": False, "paid_date": None, "transaction_id": None})
    db.query(models.ExpenseProposal).filter_by(transaction_id=transaction_id).update({"transaction_id": None})
    db.delete(db_txn)
    db.commit()
    return {"deleted": True, "id": transaction_id}


@app.patch("/transactions/item/{transaction_id}", response_model=schemas.TransactionOut, dependencies=[Depends(auth.authorize)])
def update_transaction(transaction_id: int, txn: schemas.TransactionCreate, user=Depends(auth.current_user), db: Session = Depends(get_db)):
    item = db.get(models.Transaction, transaction_id)
    if db.query(models.BillPayment).filter_by(transaction_id=transaction_id, paid=True).first():
        raise HTTPException(409, "This is a linked bill payment. Mark the bill unpaid to replace its payment.")
    for key, value in txn.model_dump(exclude={"user_id"}).items():
        setattr(item, key, normalize_category(value) if key == "category" else value)
    item.user_id = user.id
    db.commit()
    return item


# ---------- Pace tracking / burn rate ----------

@app.get("/pace/{user_id}/{category}", response_model=schemas.PaceStatus, dependencies=[Depends(auth.authorize)])
def get_pace(user_id: int, category: str, year: int, month: int, db: Session = Depends(get_db)):
    result = services.calculate_pace(db, user_id, category, year, month)
    if result is None:
        raise HTTPException(status_code=404, detail="No budget set for this category/month")
    return result


@app.get("/pace/{user_id}", response_model=list[schemas.PaceStatus], dependencies=[Depends(auth.authorize)])
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

@app.post("/buy-decision", response_model=schemas.BuyDecisionResponse, dependencies=[Depends(auth.authorize)])
def buy_decision(req: schemas.BuyDecisionRequest, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    req.user_id = user.id
    return services.evaluate_purchase(db, req.user_id, normalize_category(req.category), req.item_cost, req.year, req.month)


# ---------- AI Financial Coach ----------

def _get_pace_data(db: Session, user_id: int, year: int, month: int) -> list[dict]:
    budgets = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user_id,
            models.Budget.year == year,
            models.Budget.month == month,
        )
        .all()
    )
    pace_data = []
    for b in budgets:
        r = services.calculate_pace(db, user_id, b.category, year, month)
        if r:
            pace_data.append(r)
    return pace_data


def _get_month_transactions(db: Session, user_id: int, year: int, month: int):
    from sqlalchemy import func as sa_func

    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date <= date.today(),
            sa_func.extract("year", models.Transaction.date) == year,
            sa_func.extract("month", models.Transaction.date) == month,
        )
        .order_by(models.Transaction.date.desc())
        .all()
    )


def _raise_for_llm_error(e: Exception):
    if isinstance(e, RuntimeError):
        raise HTTPException(status_code=503, detail="AI service unavailable. Check server configuration or retry shortly.")
    error_text = str(e)
    if "429" in error_text or "quota" in error_text.lower() or "rate limit" in error_text.lower():
        raise HTTPException(
            status_code=429,
            detail="The AI coach has hit its usage limit for now. Please try again in a minute.",
        )
    raise HTTPException(
        status_code=502,
        detail="The AI coach couldn't respond right now. Please try again shortly.",
    )


@app.get("/coach/{user_id}", response_model=schemas.CoachResponse, dependencies=[Depends(auth.authorize)])
def get_coaching(user_id: int, year: int = None, month: int = None, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today = date.today()
    target_year = year or today.year
    target_month = month or today.month
    pace_data = _get_pace_data(db, user_id, target_year, target_month)

    try:
        advice = llm_coach.get_coaching_advice(user.name, user.monthly_income, pace_data)
    except Exception as e:
        _raise_for_llm_error(e)

    return {"advice": advice}


@app.get("/coach/history/{user_id}", response_model=list[schemas.ChatMessageOut], dependencies=[Depends(auth.authorize)])
def get_coach_history(user_id: int, db: Session = Depends(get_db)):
    return list(reversed(
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == user_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(100)
        .all()
    ))


@app.delete("/coach/history/{user_id}", dependencies=[Depends(auth.authorize)])
def clear_coach_history(user_id: int, db: Session = Depends(get_db)):
    deleted = db.query(models.ChatMessage).filter(models.ChatMessage.user_id == user_id).delete()
    db.commit()
    return {"deleted": deleted}


@app.post("/coach/chat/{user_id}", response_model=schemas.CoachChatResponse, dependencies=[Depends(auth.authorize)])
def coach_chat(
    user_id: int,
    req: schemas.CoachChatRequest,
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    pace_data = _get_pace_data(db, user_id, target_year, target_month)
    month_txns = _get_month_transactions(db, user_id, target_year, target_month)
    total_spent = sum(t.amount for t in month_txns)
    remaining = user.monthly_income - total_spent
    recent_transactions = [
        {
            "date": t.date.isoformat(),
            "amount": t.amount,
            "category": t.category,
            "merchant": t.merchant,
        }
        for t in month_txns[:15]
    ]

    db_history = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == user_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(100)
        .all()
    )
    history = []
    context_size = 0
    for message in db_history[:20]:
        if context_size + len(message.content) > 20000:
            break
        context_size += len(message.content)
        history.insert(0, {"role": message.role, "content": message.content})

    anomalies = services.get_anomalies(db, user_id, target_year, target_month)
    subscriptions = services.detect_recurring_subscriptions(db, user_id)

    if db.query(models.ExpenseProposal).filter_by(user_id=user_id, state="pending").count() >= 90:
        raise HTTPException(409, "Review your pending expense proposals before continuing")
    proposed_expenses = []

    def log_expense(amount: float, category: str, merchant: str = None, note: str = None, txn_date: str = None) -> dict:
        """Propose an expense for explicit user review. This does not record spending until the user presses Save.

        Args:
            amount: The amount spent, in INR.
            category: Best-fit spending category (e.g. Food, Groceries, Transport, Shopping, Entertainment, Bills, Health, Miscellaneous).
            merchant: Merchant or place name, if the user mentioned one.
            note: A short description of what the expense was for (e.g. "breakfast").
            txn_date: Date of the expense as YYYY-MM-DD. Defaults to today if not given.
        """
        parsed_date = date.today()
        if txn_date:
            try:
                parsed_date = date.fromisoformat(txn_date)
            except ValueError:
                raise ValueError("Invalid expense date")

        resolved_category = services.resolve_transaction_category(
            db, user_id, category, parsed_date.year, parsed_date.month
        )
        validated = schemas.TransactionCreate(user_id=user_id, amount=amount, category=category, date=parsed_date, note=note, merchant=merchant, source="chat")
        if len(proposed_expenses) >= 10:
            raise ValueError("At most 10 expense proposals per chat request")
        payload = validated.model_dump(mode="json", exclude={"user_id"})
        payload["category"] = resolved_category
        proposal_id = str(uuid.uuid4())
        db.add(models.ExpenseProposal(id=proposal_id, user_id=user_id, payload=json.dumps(payload), state="pending"))
        proposed_expenses.append({"id": proposal_id, **payload})
        return {"status": "awaiting_user_save", "amount": amount, "category": resolved_category, "date": parsed_date.isoformat()}

    try:
        reply = llm_coach.chat_reply(
            user.name,
            user.monthly_income,
            pace_data,
            total_spent,
            remaining,
            recent_transactions,
            history,
            req.message,
            anomalies,
            subscriptions,
            log_expense_fn=log_expense,
        )
    except Exception as e:
        _raise_for_llm_error(e)

    db.add(models.ChatMessage(user_id=user_id, role="user", content=req.message))
    db.add(models.ChatMessage(user_id=user_id, role="model", content=reply))
    db.commit()

    return {"reply": reply, "logged_expenses": [], "proposed_expenses": proposed_expenses}


@app.get("/coach/proposals/{user_id}", response_model=list[schemas.ProposedExpense], dependencies=[Depends(auth.authorize)])
def pending_proposals(user_id: int, db: Session = Depends(get_db)):
    rows = db.query(models.ExpenseProposal).filter_by(user_id=user_id, state="pending").limit(100).all()
    return [{"id": p.id, **json.loads(p.payload)} for p in rows]


@app.post("/coach/proposals/{proposal_id}/{action}", dependencies=[Depends(auth.authorize)])
def resolve_proposal(proposal_id: str, action: str, user=Depends(auth.current_user), db: Session = Depends(get_db)):
    from sqlalchemy import text
    if action not in {"save", "cancel"}:
        raise HTTPException(404, "Unknown action")
    user_id = user.id
    db.rollback()
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    proposal = db.query(models.ExpenseProposal).filter_by(id=proposal_id, user_id=user_id).with_for_update().first()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if proposal.state != "pending":
        if proposal.state == ("saved" if action == "save" else "cancelled"):
            return {"state": proposal.state, "transaction_id": proposal.transaction_id}
        raise HTTPException(409, "Proposal already resolved")
    if action == "save":
        data = schemas.TransactionCreate(user_id=user_id, **json.loads(proposal.payload))
        transaction = models.Transaction(**data.model_dump())
        db.add(transaction)
        db.flush()
        proposal.transaction_id = transaction.id
        proposal.state = "saved"
    else:
        proposal.state = "cancelled"
    db.commit()
    return {"state": proposal.state, "transaction_id": proposal.transaction_id}


# ---------- Smart Anomaly Detection ----------

@app.get("/anomalies/{user_id}", response_model=list[schemas.AnomalyItem], dependencies=[Depends(auth.authorize)])
def get_anomalies(user_id: int, year: int, month: int, db: Session = Depends(get_db)):
    return services.get_anomalies(db, user_id, year, month)


# ---------- Weekly Digest ----------

@app.get("/coach/digest/{user_id}", response_model=schemas.WeeklyDigestResponse, dependencies=[Depends(auth.authorize)])
def get_weekly_digest(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    digest = services.get_weekly_digest_data(db, user_id)

    try:
        digest_text = llm_coach.get_weekly_digest(user.name, digest)
    except Exception:
        digest_text = "AI narration is unavailable. The figures below show recorded non-monthly spending over the last seven days; monthly recurring payments are excluded."

    return {**digest, "digest_text": digest_text}


# ---------- Recurring Subscription Detection ----------

@app.get("/subscriptions/{user_id}", response_model=list[schemas.SubscriptionItem], dependencies=[Depends(auth.authorize)])
def get_subscriptions(user_id: int, db: Session = Depends(get_db)):
    return services.detect_recurring_subscriptions(db, user_id)


# ---------- Goal-Based Savings Simulator ----------

@app.post("/savings-goal/{user_id}", response_model=schemas.SavingsGoalResponse, dependencies=[Depends(auth.authorize)])
def savings_goal(user_id: int, req: schemas.SavingsGoalRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.target_amount <= 0 or req.months <= 0:
        raise HTTPException(status_code=422, detail="target_amount and months must be positive.")

    plan = services.compute_savings_plan(db, user_id, req.target_amount, req.months)
    if plan is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        advice = llm_coach.get_goal_advice(user.name, plan)
    except Exception:
        advice = "AI narration is unavailable. " + ("The recorded baseline supports this goal within the stated discretionary cuts." if plan["achievable"] else "This goal is not supported by reliable history and reasonable discretionary cuts. Extend the timeline or review income and missing records; fixed costs are protected.")

    return {**plan, "advice": advice}


# ---------- Automated Ingestion ----------

@app.post("/ingest/sms", response_model=list[schemas.ParsedTransactionPreview], dependencies=[Depends(auth.authorize)])
def ingest_sms(req: schemas.SmsIngestRequest):
    """Parses pasted bank SMS text (one message per line) into a preview list.
    Does NOT save anything — call /ingest/commit to actually insert."""
    try:
        parsed = ingestion.parse_sms_text(req.raw_text)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not parsed:
        raise HTTPException(
            status_code=422,
            detail="No debit transactions could be parsed from that text. "
            "Make sure each SMS is on its own line and mentions an amount (Rs./INR).",
        )
    return parsed[:500]


@app.post("/ingest/statement", response_model=list[schemas.ParsedTransactionPreview], dependencies=[Depends(auth.authorize)])
async def ingest_statement(file: UploadFile = File(...)):
    """Parses an uploaded bank statement (CSV or PDF) into a preview list.
    Does NOT save anything — call /ingest/commit to actually insert."""
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Upload exceeds 5 MiB")
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
    return parsed[:500]


@app.post("/ingest/commit", response_model=schemas.CommitIngestResponse, dependencies=[Depends(auth.authorize)])
def commit_ingest(req: schemas.CommitIngestRequest, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    req.user_id = user.id
    """Inserts a reviewed/edited batch of parsed transactions."""
    if req.idempotency_key:
        existing = db.query(models.ImportBatch).filter_by(user_id=user.id, batch_key=req.idempotency_key).first()
        if existing:
            return {"inserted": existing.inserted}
        db.add(models.ImportBatch(user_id=user.id, batch_key=req.idempotency_key, inserted=len(req.transactions)))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.query(models.ImportBatch).filter_by(user_id=user.id, batch_key=req.idempotency_key).first()
            if existing:
                return {"inserted": existing.inserted}
            raise

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

@app.post("/bills", dependencies=[Depends(auth.authorize)])
def create_bill(bill: schemas.BillCreate, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    bill.user_id = user.id
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

    return {"id": db_bill.id, "name": db_bill.name, "category": db_bill.category,
            "amount": db_bill.amount, "due_day": db_bill.due_day}


@app.get("/bills/upcoming/{user_id}", response_model=list[schemas.BillStatus], dependencies=[Depends(auth.authorize)])
def upcoming_bills(user_id: int, db: Session = Depends(get_db)):
    return services.upcoming_bills(db, user_id)


@app.get("/bills/{user_id}", response_model=list[schemas.BillStatus], dependencies=[Depends(auth.authorize)])
def list_bills(user_id: int, year: int, month: int, db: Session = Depends(get_db)):
    return services.get_bills_with_status(db, user_id, year, month)


@app.post("/bills/{bill_id}/pay", response_model=schemas.BillStatus, dependencies=[Depends(auth.authorize)])
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


@app.post("/bills/{bill_id}/unpay", response_model=schemas.BillStatus, dependencies=[Depends(auth.authorize)])
def unpay_bill(bill_id: int, year: int, month: int, db: Session = Depends(get_db)):
    services.mark_bill_unpaid(db, bill_id, year, month)
    bill = db.query(models.Bill).filter(models.Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    today = date.today()
    status = "overdue" if date(year, month, min(bill.due_day, services.get_days_in_month(year, month))) < today else "due"
    return {
        "id": bill.id, "name": bill.name, "category": bill.category,
        "amount": bill.amount, "due_day": bill.due_day,
        "status": status, "paid_date": None,
    }


@app.delete("/bills/{bill_id}", dependencies=[Depends(auth.authorize)])
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print(json.dumps({"event": "startup_stage", "stage": "application_import", "status": "complete", "elapsed_seconds": round(time.monotonic() - _import_started, 3)}), flush=True)
