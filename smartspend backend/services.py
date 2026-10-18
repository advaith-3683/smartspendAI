from decimal import Decimal, ROUND_HALF_UP, getcontext
getcontext().rounding = ROUND_HALF_UP
import calendar
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from utils import normalize_category

MISCELLANEOUS = "Miscellaneous"
DEFAULT_MISC_LIMIT = Decimal("2000.0")


def resolve_transaction_category(db: Session, user_id: int, raw_category: str, year: int, month: int) -> str:
    """Preserve the category; budgets are always an explicit user decision."""
    return normalize_category(raw_category)


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

    category = normalize_category(category)
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
    days_elapsed = today.day if (today.year == year and today.month == month) else (days_in_month if date(year, month, 1) < today else 0)
    # Future months have zero elapsed days and no incurred spending.

    txns = (
        db.query(models.Transaction.amount, models.Transaction.frequency)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.category == category,
            models.Transaction.date <= today,
            func.extract("year", models.Transaction.date) == year,
            func.extract("month", models.Transaction.date) == month,
        )
        .all()
    )
    daily_spent = sum((amount for amount, freq in txns if freq == "daily"), Decimal(0))
    monthly_spent = sum((amount for amount, freq in txns if freq != "daily"), Decimal(0))
    spent_so_far = daily_spent + monthly_spent

    # Monthly (recurring/lump-sum) spend already happened in full — it isn't
    # paced across the month, so it's added once rather than projected daily.
    daily_rate = daily_spent / max(days_elapsed, 1)
    projected_spend = (daily_rate * days_in_month) + monthly_spent
    percent_of_budget_projected = (
        (projected_spend / budget.monthly_limit) * 100 if budget.monthly_limit > 0 else 0
    )

    if spent_so_far > budget.monthly_limit:
        status = "over_budget"
    elif daily_spent == 0:
        # No ongoing daily spend to project — this category is either untouched
        # or fully settled by a one-time/monthly payment. Status should reflect
        # whether that payment fit the budget, not a fabricated future risk.
        status = "over_budget" if spent_so_far > budget.monthly_limit else "on_track"
    elif percent_of_budget_projected > 100:
        status = "at_risk"
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
    category = normalize_category(category)
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
    spent_so_far = sum((row[0] for row in (
        db.query(models.Transaction.amount)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date <= date.today(),
            models.Transaction.category == category,
            func.extract("year", models.Transaction.date) == year,
            func.extract("month", models.Transaction.date) == month,
        )
        .all()
    )), Decimal(0))

    if budget is None:
        return {"category": category, "item_cost": item_cost, "budget_exists": False, "remaining_budget_before": None, "remaining_budget_after": None, "would_exceed_budget": None, "message": "No budget exists for this category and selected month. Set one to assess this purchase."}
    limit = budget.monthly_limit
    remaining_before = limit - spent_so_far
    remaining_after = remaining_before - item_cost
    would_exceed = remaining_after < 0

    if would_exceed:
        message = (
            f"This would put you {abs(remaining_after):.2f} over your {category} budget. "
            f"Consider waiting or trimming spend elsewhere this month."
        )
    elif remaining_after < limit * Decimal("0.1"):
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
    return sum((row[0] for row in (
        db.query(models.Transaction.amount)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.category == category,
            models.Transaction.date >= start,
            models.Transaction.date <= end_inclusive,
            models.Transaction.frequency != "monthly",
        )
        .all()
    )), Decimal(0))


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

        if prior_week >= 200 and this_week >= prior_week * Decimal("1.5"):
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
                func.extract("year", models.Transaction.date) == year,
                func.extract("month", models.Transaction.date) == month,
                models.Transaction.frequency != "monthly",
                models.Transaction.date <= date.today(),
            )
            .all()
        )
        if not txns:
            continue

        weekend_total = Decimal("0.0")
        weekday_total = Decimal("0.0")
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
    today = date.today()
    categories = [row[0] for row in db.query(models.Transaction.category).filter(
        models.Transaction.user_id == user_id,
        models.Transaction.date >= date(year, month, 1),
        models.Transaction.date <= min(today, date(year, month, get_days_in_month(year, month))),
    ).distinct().all()]
    spikes = detect_spending_spikes(db, user_id, categories, today) if (year, month) == (today.year, today.month) else []
    patterns = detect_weekend_patterns(db, user_id, categories, year, month)
    for pattern in patterns:
        pattern["message"] = pattern["message"].replace("this month", f"in {year}-{month:02}")
    return spikes + patterns


# ---------- Weekly Digest ----------

def get_weekly_digest_data(db: Session, user_id: int, today: date = None):
    """Gathers everything needed for Coco's weekly digest: this week vs last
    week totals, top categories, any anomalies/subscriptions/bills due —
    reusing the same detection logic already used elsewhere in the app."""
    if today is None:
        today = date.today()

    this_week_start = today - timedelta(days=6)
    prior_week_start = today - timedelta(days=13)
    prior_week_end = today - timedelta(days=7)

    this_week_txns = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= this_week_start,
            models.Transaction.date <= today,
            models.Transaction.frequency != "monthly",
        )
        .all()
    )
    total_this_week = sum(t.amount for t in this_week_txns)

    total_last_week = sum((row[0] for row in (
        db.query(models.Transaction.amount)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= prior_week_start,
            models.Transaction.date <= prior_week_end,
            models.Transaction.frequency != "monthly",
        )
        .all()
    )), Decimal(0))

    by_category = {}
    for t in this_week_txns:
        by_category[t.category] = by_category.get(t.category, Decimal("0.0")) + t.amount
    top_categories = [
        {"category": c, "amount": round(a, 2)}
        for c, a in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)[:3]
    ]

    anomalies = get_anomalies(db, user_id, today.year, today.month)
    subscriptions = detect_recurring_subscriptions(db, user_id)

    bills_due_soon = upcoming_bills(db, user_id, today)

    return {
        "period_start": this_week_start,
        "period_end": today,
        "total_this_week": round(total_this_week, 2),
        "total_last_week": round(total_last_week, 2),
        "top_categories": top_categories,
        "anomalies": anomalies,
        "subscriptions": subscriptions,
        "bills_due_soon": bills_due_soon,
    }


def upcoming_bills(db: Session, user_id: int, today: date = None):
    today = today or date.today()
    bills_due_soon = []
    templates = db.query(models.Bill).filter_by(user_id=user_id).all()
    paid = {(p.bill_id, p.year, p.month) for p in db.query(models.BillPayment).join(models.Bill).filter(
        models.Bill.user_id == user_id, models.BillPayment.paid == True).all()}
    horizon = today + timedelta(days=7)
    for bill in templates:
        created = bill.created_at.date() if bill.created_at else today
        period = created.replace(day=1)
        while period <= horizon:
            due = date(period.year, period.month, min(bill.due_day, get_days_in_month(period.year, period.month)))
            if due <= horizon and (bill.id, period.year, period.month) not in paid:
                bills_due_soon.append({"id": bill.id, "name": bill.name, "category": bill.category,
                    "amount": bill.amount, "due_day": due.day, "due_date": due,
                    "status": "overdue" if due < today else "due", "paid_date": None})
            period = (period + timedelta(days=32)).replace(day=1)
    bills_due_soon.sort(key=lambda b: b["due_date"])

    return bills_due_soon


# ---------- Goal-Based Savings Simulator ----------

MAX_CATEGORY_CUT_RATIO = Decimal("0.6")  # never suggest cutting more than 60% out of one category

# Categories that are essentially fixed/contractual and unrealistic to "cut" —
# excluded from the cuttable pool so the plan doesn't suggest slashing rent 60%.
FIXED_COST_KEYWORDS = {"rent", "emi", "loan", "insurance", "mortgage", "tuition", "school fees", "bills"}


def _is_fixed_cost(category: str) -> bool:
    lowered = category.strip().lower()
    return any(keyword in lowered for keyword in FIXED_COST_KEYWORDS)


def compute_savings_plan(db: Session, user_id: int, target_amount: float, months: int, lookback_months: int = 3):
    """Deterministic (non-LLM) calculation of what monthly cut per category is
    needed to reach a savings goal, based on each category's real average
    monthly spend over the last `lookback_months` months that have data."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None

    end = date.today().replace(day=1)
    index = end.year * 12 + end.month - 1 - lookback_months
    cutoff = date(index // 12, index % 12 + 1, 1)
    txns = (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == user_id, models.Transaction.date >= cutoff, models.Transaction.date < end)
        .all()
    )

    # category -> {(year, month): total}
    by_category_month: dict[str, dict] = {}
    for t in txns:
        key = t.category
        month_key = (t.date.year, t.date.month)
        by_category_month.setdefault(key, {}).setdefault(month_key, Decimal("0.0"))
        by_category_month[key][month_key] += t.amount

    baselines = {}
    for category, months_map in by_category_month.items():
        num_months = lookback_months
        baselines[category] = sum(months_map.values()) / num_months

    total_baseline = sum(baselines.values())
    monthly_savings_needed = target_amount / months if months > 0 else Decimal("0.0")
    current_monthly_savings = user.monthly_income - total_baseline
    additional_cut_needed = max(monthly_savings_needed - current_monthly_savings, Decimal("0.0"))

    # Only discretionary (non-fixed-cost) categories are eligible for cuts.
    fixed_categories = {b.category for b in db.query(models.Bill).filter_by(user_id=user_id).all()}
    discretionary_total = sum(v for k, v in baselines.items() if not _is_fixed_cost(k) and k not in fixed_categories)
    pool_total = discretionary_total

    if pool_total <= 0 or additional_cut_needed <= 0:
        cut_ratio = Decimal("0.0")
    else:
        cut_ratio = min(additional_cut_needed / pool_total, MAX_CATEGORY_CUT_RATIO)

    achieved_cut = pool_total * cut_ratio
    observed_months = len({(t.date.year, t.date.month) for t in txns})
    reliable = observed_months == lookback_months and user.created_at is not None and user.created_at.date() <= cutoff
    achievable = reliable and achieved_cut >= additional_cut_needed - Decimal("0.01")

    categories = []
    for category, avg in sorted(baselines.items(), key=lambda kv: kv[1], reverse=True):
        applies = not _is_fixed_cost(category) and category not in fixed_categories
        effective_ratio = cut_ratio if applies else Decimal("0.0")
        cut_amount = avg * effective_ratio
        categories.append({
            "category": category,
            "current_monthly_avg": round(avg, 2),
            "target_monthly": round(avg - cut_amount, 2),
            "cut_amount": round(cut_amount, 2),
            "cut_percent": round(effective_ratio * 100, 1),
        })

    return {
        "history_months": observed_months,
        "history_reliable": reliable,
        "baseline_note": f"Baseline uses {cutoff} through {end - timedelta(days=1)} across {lookback_months} full calendar months, including zero-spend months. Current-month and future entries excluded. " + ("History covers this window; unrecorded expenses can still affect the estimate." if reliable else "Insufficient history: this is a provisional estimate, not a reliable monthly baseline."),
        "target_amount": target_amount,
        "months": months,
        "monthly_savings_needed": round(monthly_savings_needed, 2),
        "current_monthly_income": user.monthly_income,
        "current_baseline_spend": round(total_baseline, 2),
        "current_monthly_savings": round(current_monthly_savings, 2),
        "additional_cut_needed": round(additional_cut_needed, 2),
        "achievable": achievable,
        "categories": categories,
    }


# ---------- Recurring Subscription Detection ----------

def detect_recurring_subscriptions(db: Session, user_id: int, lookback_months: int = 6):
    """Scans transaction history for merchants that charge a similar amount
    repeatedly across different months — a strong signal of a subscription
    or recurring payment the user may have forgotten about.

    Heuristic: group by merchant, require the merchant to appear in at least
    2 distinct calendar months within the lookback window, with amounts that
    stay within 15% of the average (recurring charges are usually fixed-price,
    unlike e.g. groceries at the same store)."""
    cutoff = date.today() - timedelta(days=30 * lookback_months)

    txns = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.merchant.isnot(None),
            models.Transaction.merchant != "",
            models.Transaction.date >= cutoff,
            models.Transaction.date <= date.today(),
        )
        .order_by(models.Transaction.date.asc())
        .all()
    )

    by_merchant: dict[str, list] = {}
    for t in txns:
        key = t.merchant.strip().lower()
        by_merchant.setdefault(key, []).append(t)

    subscriptions = []
    for merchant_key, group in by_merchant.items():
        months_seen = {(t.date.year, t.date.month) for t in group}
        if len(months_seen) < 2:
            continue

        amounts = [t.amount for t in group]
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount <= 0:
            continue

        within_tolerance = all(abs(a - avg_amount) / avg_amount <= Decimal("0.15") for a in amounts)
        if not within_tolerance:
            continue

        display_name = group[-1].merchant  # most recent original-cased spelling
        last_txn = group[-1]
        subscriptions.append({
            "merchant": display_name,
            "category": last_txn.category,
            "average_amount": round(avg_amount, 2),
            "occurrences": len(group),
            "months_seen": len(months_seen),
            "last_charged": last_txn.date,
            "message": (
                f"{display_name} has charged you ~₹{avg_amount:,.0f} in "
                f"{len(months_seen)} different months — looks like a recurring "
                f"subscription. Last charge: {last_txn.date.isoformat()}."
            ),
        })

    subscriptions.sort(key=lambda s: s["average_amount"], reverse=True)
    return subscriptions


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
        if payment and payment.paid and payment.transaction_id and db.get(models.Transaction, payment.transaction_id):
            status = "paid"
            paid_date = payment.paid_date
        elif date(year, month, min(bill.due_day, get_days_in_month(year, month))) < today:
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
            "due_day": min(bill.due_day, get_days_in_month(year, month)),
            "due_date": date(year, month, min(bill.due_day, get_days_in_month(year, month))),
            "status": status,
            "paid_date": paid_date,
        })
    return results


def mark_bill_paid(db: Session, bill_id: int, year: int, month: int, today: date = None):
    if today is None:
        today = date.today()

    from sqlalchemy import text
    db.rollback()
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    else:
        db.query(models.Bill).filter_by(id=bill_id).with_for_update().first()
    bill = db.query(models.Bill).filter(models.Bill.id == bill_id).first()
    if not bill:
        return None

    payment = (
        db.query(models.BillPayment)
        .filter(models.BillPayment.bill_id == bill_id, models.BillPayment.year == year, models.BillPayment.month == month)
        .first()
    )
    if payment and payment.paid and payment.transaction_id and db.get(models.Transaction, payment.transaction_id):
        return payment  # already paid, no-op

    # The transaction must be dated within the (year, month) being paid for —
    # not real-world "today" — otherwise marking a June bill paid while
    # viewing June would silently log it in whatever month "today" falls in.
    # Anchor it to the bill's due day (clamped to that month's length).
    days_in_target_month = get_days_in_month(year, month)
    txn_date = date(year, month, min(bill.due_day, days_in_target_month))

    # Log the payment as a transaction so it counts toward the budget/pace tracking,
    # tagged 'monthly' so it isn't paced as a recurring daily cost. Bills always get
    # their own dedicated category row — never the generic Miscellaneous fallback.
    resolved_category = normalize_category(bill.category)
    txn = models.Transaction(
        user_id=bill.user_id,
        amount=bill.amount,
        category=resolved_category,
        date=txn_date,
        note=f"{bill.name} bill payment",
        merchant=bill.name,
        source="bill",
        frequency="monthly",
    )
    db.add(txn)
    db.flush()

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
    from sqlalchemy import text
    db.rollback()
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    else:
        db.query(models.Bill).filter_by(id=bill_id).with_for_update().first()
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
