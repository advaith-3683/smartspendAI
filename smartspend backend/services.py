import calendar
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from utils import normalize_category

MISCELLANEOUS = "Miscellaneous"
DEFAULT_MISC_LIMIT = 2000.0


def ensure_category_budget(db: Session, user_id: int, raw_category: str, year: int, month: int, default_limit: float) -> str:
    """Guarantees the given category has its own budget row for this month —
    creating one with default_limit if missing — rather than falling back to
    a shared bucket. Used for bills, which should always get their own row."""
    category = normalize_category(raw_category)
    existing = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user_id,
            models.Budget.category == category,
            models.Budget.year == year,
            models.Budget.month == month,
        )
        .first()
    )
    if not existing:
        db.add(models.Budget(
            user_id=user_id, category=category, monthly_limit=default_limit, month=month, year=year,
        ))
        db.commit()
    return category


def resolve_transaction_category(db: Session, user_id: int, raw_category: str, year: int, month: int) -> str:
    """If the typed category has no budget for that month, fall back to a
    'Miscellaneous' bucket so the spend is still tracked and visible, instead
    of silently creating an ungoverned category with no gauge."""
    category = normalize_category(raw_category)

    existing = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user_id,
            models.Budget.category == category,
            models.Budget.year == year,
            models.Budget.month == month,
        )
        .first()
    )
    if existing:
        return category

    misc_budget = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user_id,
            models.Budget.category == MISCELLANEOUS,
            models.Budget.year == year,
            models.Budget.month == month,
        )
        .first()
    )
    if not misc_budget:
        misc_budget = models.Budget(
            user_id=user_id,
            category=MISCELLANEOUS,
            monthly_limit=DEFAULT_MISC_LIMIT,
            month=month,
            year=year,
        )
        db.add(misc_budget)
        db.commit()

    return MISCELLANEOUS


def get_days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def calculate_pace(db: Session, user_id: int, category: str, year: int, month: int, today: date = None):
    """
    Pace tracking calculation.
    Example: budget=10000 for 30 days, spent 5000 by day 10
    -> daily_rate = 500, projected_spend = 500 * 30 = 15000 (50% over budget)
    """
    if today is None:
        today = date.today()

    budget = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user_id,
            models.Budget.category == category,
            models.Budget.year == year,
            models.Budget.month == month,
        )
        .first()
    )
    if budget is None:
        return None

    days_in_month = get_days_in_month(year, month)
    days_elapsed = today.day if (today.year == year and today.month == month) else days_in_month
    days_elapsed = max(days_elapsed, 1)  # avoid divide-by-zero on day 1

    txns = (
        db.query(models.Transaction.amount, models.Transaction.frequency)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.category == category,
            func.strftime("%Y", models.Transaction.date) == str(year),
            func.strftime("%m", models.Transaction.date) == f"{month:02d}",
        )
        .all()
    )
    daily_spent = sum(amount for amount, freq in txns if freq != "monthly")
    monthly_spent = sum(amount for amount, freq in txns if freq == "monthly")
    spent_so_far = daily_spent + monthly_spent

    # Monthly (recurring/lump-sum) spend already happened in full — it isn't
    # paced across the month, so it's added once rather than projected daily.
    daily_rate = daily_spent / days_elapsed
    projected_spend = (daily_rate * days_in_month) + monthly_spent
    percent_of_budget_projected = (
        (projected_spend / budget.monthly_limit) * 100 if budget.monthly_limit > 0 else 0
    )

    if daily_spent == 0:
        # No ongoing daily spend to project — this category is either untouched
        # or fully settled by a one-time/monthly payment. Status should reflect
        # whether that payment fit the budget, not a fabricated future risk.
        status = "over_budget" if spent_so_far > budget.monthly_limit else "on_track"
    elif percent_of_budget_projected > 100:
        status = "over_budget"
    elif percent_of_budget_projected >= 85:
        status = "at_risk"
    else:
        status = "on_track"

    return {
        "category": category,
        "monthly_limit": budget.monthly_limit,
        "spent_so_far": round(spent_so_far, 2),
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "projected_spend": round(projected_spend, 2),
        "percent_of_budget_projected": round(percent_of_budget_projected, 2),
        "status": status,
    }


def evaluate_purchase(db: Session, user_id: int, category: str, item_cost: float, year: int, month: int):
    """'Should I Buy This?' calculator."""
    budget = (
        db.query(models.Budget)
        .filter(
            models.Budget.user_id == user_id,
            models.Budget.category == category,
            models.Budget.year == year,
            models.Budget.month == month,
        )
        .first()
    )
    spent_so_far = (
        db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.category == category,
            func.strftime("%Y", models.Transaction.date) == str(year),
            func.strftime("%m", models.Transaction.date) == f"{month:02d}",
        )
        .scalar()
    )

    limit = budget.monthly_limit if budget else 0.0
    remaining_before = limit - spent_so_far
    remaining_after = remaining_before - item_cost
    would_exceed = remaining_after < 0

    if would_exceed:
        message = (
            f"This would put you {abs(remaining_after):.2f} over your {category} budget. "
            f"Consider waiting or trimming spend elsewhere this month."
        )
    elif remaining_after < limit * 0.1:
        message = (
            f"You can afford it, but it uses almost all of your remaining {category} budget "
            f"({remaining_after:.2f} left afterward). Proceed carefully."
        )
    else:
        message = f"You're clear. {remaining_after:.2f} will remain in your {category} budget."

    return {
        "category": category,
        "item_cost": item_cost,
        "remaining_budget_before": round(remaining_before, 2),
        "remaining_budget_after": round(remaining_after, 2),
        "would_exceed_budget": would_exceed,
        "message": message,
    }


def _category_sum(db: Session, user_id: int, category: str, start: date, end_inclusive: date) -> float:
    return (
        db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.category == category,
            models.Transaction.date >= start,
            models.Transaction.date <= end_inclusive,
            models.Transaction.frequency != "monthly",
        )
        .scalar()
    )


def detect_spending_spikes(db: Session, user_id: int, categories: list[str], today: date = None):
    """Compare the last 7 days of spend per category against the 7 days before that.
    Flags a spike if this week is at least 1.5x the prior week (and the prior week
    had meaningful spend, to avoid noise from brand-new categories)."""
    if today is None:
        today = date.today()

    this_week_start = today - timedelta(days=6)
    prior_week_start = today - timedelta(days=13)
    prior_week_end = today - timedelta(days=7)

    anomalies = []
    for category in categories:
        this_week = _category_sum(db, user_id, category, this_week_start, today)
        prior_week = _category_sum(db, user_id, category, prior_week_start, prior_week_end)

        if prior_week >= 200 and this_week >= prior_week * 1.5:
            multiplier = this_week / prior_week
            anomalies.append({
                "category": category,
                "type": "spike",
                "message": (
                    f"You spent {multiplier:.1f}x your usual amount on {category} this week "
                    f"(₹{this_week:,.0f} vs ₹{prior_week:,.0f} the week before). "
                    f"Consider slowing down on {category} for the next few days to balance it out."
                ),
            })
    return anomalies


def detect_weekend_patterns(db: Session, user_id: int, categories: list[str], year: int, month: int):
    """Compares average daily weekend spend vs average daily weekday spend per
    category this month. Flags categories where weekend spending is disproportionate."""
    days_in_month = get_days_in_month(year, month)
    anomalies = []

    for category in categories:
        txns = (
            db.query(models.Transaction.date, models.Transaction.amount)
            .filter(
                models.Transaction.user_id == user_id,
                models.Transaction.category == category,
                func.strftime("%Y", models.Transaction.date) == str(year),
                func.strftime("%m", models.Transaction.date) == f"{month:02d}",
                models.Transaction.frequency != "monthly",
            )
            .all()
        )
        if not txns:
            continue

        weekend_total = 0.0
        weekday_total = 0.0
        weekend_days = 0
        weekday_days = 0
        seen_days = set()

        for d in range(1, days_in_month + 1):
            day_date = date(year, month, d)
            if day_date > date.today():
                break
            if day_date.weekday() >= 5:  # Sat=5, Sun=6
                weekend_days += 1
            else:
                weekday_days += 1

        for txn_date, amount in txns:
            if txn_date.weekday() >= 5:
                weekend_total += amount
            else:
                weekday_total += amount

        if weekend_days == 0 or weekday_days == 0:
            continue

        weekend_avg = weekend_total / weekend_days
        weekday_avg = weekday_total / weekday_days

        if weekday_avg > 0 and weekend_avg >= weekday_avg * 2 and weekend_total >= 300:
            ratio = weekend_avg / weekday_avg
            anomalies.append({
                "category": category,
                "type": "weekend_pattern",
                "message": (
                    f"Your weekend spending in {category} is {ratio:.1f}x higher than "
                    f"weekdays this month (₹{weekend_avg:,.0f}/day vs ₹{weekday_avg:,.0f}/day). "
                    f"Planning weekend activities ahead could help keep this in check."
                ),
            })
    return anomalies


def get_anomalies(db: Session, user_id: int, year: int, month: int):
    budgets = (
        db.query(models.Budget)
        .filter(models.Budget.user_id == user_id, models.Budget.year == year, models.Budget.month == month)
        .all()
    )
    categories = [b.category for b in budgets]
    if not categories:
        return []

    today = date.today()
    spikes = detect_spending_spikes(db, user_id, categories, today)
    patterns = detect_weekend_patterns(db, user_id, categories, year, month)
    return spikes + patterns


# ---------- Monthly Bills ----------

def get_bills_with_status(db: Session, user_id: int, year: int, month: int, today: date = None):
    if today is None:
        today = date.today()

    bills = db.query(models.Bill).filter(models.Bill.user_id == user_id).all()
    results = []
    for bill in bills:
        payment = (
            db.query(models.BillPayment)
            .filter(
                models.BillPayment.bill_id == bill.id,
                models.BillPayment.year == year,
                models.BillPayment.month == month,
            )
            .first()
        )
        if payment and payment.paid:
            status = "paid"
            paid_date = payment.paid_date
        elif today.year == year and today.month == month and today.day > bill.due_day:
            status = "overdue"
            paid_date = None
        else:
            status = "due"
            paid_date = None

        results.append({
            "id": bill.id,
            "name": bill.name,
            "category": bill.category,
            "amount": bill.amount,
            "due_day": bill.due_day,
            "status": status,
            "paid_date": paid_date,
        })
    return results


def mark_bill_paid(db: Session, bill_id: int, year: int, month: int, today: date = None):
    if today is None:
        today = date.today()

    bill = db.query(models.Bill).filter(models.Bill.id == bill_id).first()
    if not bill:
        return None

    payment = (
        db.query(models.BillPayment)
        .filter(models.BillPayment.bill_id == bill_id, models.BillPayment.year == year, models.BillPayment.month == month)
        .first()
    )
    if payment and payment.paid:
        return payment  # already paid, no-op

    # Log the payment as a transaction so it counts toward the budget/pace tracking,
    # tagged 'monthly' so it isn't paced as a recurring daily cost. Bills always get
    # their own dedicated category row — never the generic Miscellaneous fallback.
    resolved_category = ensure_category_budget(db, bill.user_id, bill.category, year, month, default_limit=bill.amount)
    txn = models.Transaction(
        user_id=bill.user_id,
        amount=bill.amount,
        category=resolved_category,
        date=today,
        note=f"{bill.name} bill payment",
        merchant=bill.name,
        source="bill",
        frequency="monthly",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    if payment:
        payment.paid = True
        payment.paid_date = today
        payment.transaction_id = txn.id
    else:
        payment = models.BillPayment(
            bill_id=bill_id, year=year, month=month, paid=True, paid_date=today, transaction_id=txn.id
        )
        db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def mark_bill_unpaid(db: Session, bill_id: int, year: int, month: int):
    payment = (
        db.query(models.BillPayment)
        .filter(models.BillPayment.bill_id == bill_id, models.BillPayment.year == year, models.BillPayment.month == month)
        .first()
    )
    if not payment:
        return None

    if payment.transaction_id:
        txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
        if txn:
            db.delete(txn)

    payment.paid = False
    payment.paid_date = None
    payment.transaction_id = None
    db.commit()
    db.refresh(payment)
    return payment
