from datetime import date, datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, field_validator, model_validator, Field


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def validate_fields(cls, value, info):
        name = info.field_name
        if name in {"amount", "monthly_income", "monthly_limit", "item_cost", "target_amount"}:
            value = Decimal(str(value))
            if not value.is_finite() or value > Decimal("1000000000") or value < 0 or (name != "monthly_income" and value == 0):
                raise ValueError("Money must be finite, positive (income may be zero), and at most 1 billion")
            if value != value.quantize(Decimal("0.01")):
                raise ValueError("Money allows at most two decimal places")
        if name in {"name", "category", "item_name", "message", "raw_text"} and not value:
            raise ValueError("Text must not be empty")
        if isinstance(value, str) and len(value) > {"message": 4000, "raw_text": 100000, "note": 1000, "password": 128}.get(name, 100):
            raise ValueError("Text exceeds allowed length")
        if name == "month" and value is not None and not 1 <= value <= 12:
            raise ValueError("Invalid month")
        if name == "year" and value is not None and not 1900 <= value <= 2200:
            raise ValueError("Invalid year")
        if name == "due_day" and not 1 <= value <= 31:
            raise ValueError("Invalid due day")
        if name == "months" and not 1 <= value <= 600:
            raise ValueError("Months must be between 1 and 600")
        if name == "source" and value not in {"manual", "statement", "sms", "bill", "chat"}:
            raise ValueError("Invalid source")
        if name == "frequency" and value not in {"daily", "monthly", "one_time"}:
            raise ValueError("Invalid frequency")
        if name == "date" and not 1900 <= value.year <= 2200:
            raise ValueError("Invalid date")
        return value



class UserCreate(InputModel):
    name: str
    monthly_income: Decimal


class UserOut(BaseModel):
    id: int
    name: str
    monthly_income: float

    class Config:
        from_attributes = True


class BudgetCreate(InputModel):
    user_id: int
    category: str
    monthly_limit: Decimal
    month: int
    year: int


class BudgetOut(BaseModel):
    id: int
    user_id: int
    category: str
    monthly_limit: float
    month: int
    year: int

    class Config:
        from_attributes = True


class TransactionCreate(InputModel):
    user_id: int
    amount: Decimal
    category: str
    date: date
    note: Optional[str] = None
    merchant: Optional[str] = None
    source: str = "manual"
    frequency: str = "daily"


class TransactionOut(BaseModel):
    id: int
    user_id: int
    amount: float
    category: str
    date: date
    note: Optional[str]
    merchant: Optional[str]
    source: str
    frequency: str

    class Config:
        from_attributes = True


class PaceStatus(BaseModel):
    category: str
    monthly_limit: float
    spent_so_far: float
    days_elapsed: int
    days_in_month: int
    projected_spend: float
    percent_of_budget_projected: float
    status: str  # "on_track" | "at_risk" | "over_budget"


class BuyDecisionRequest(InputModel):
    year: int
    month: int
    user_id: int
    category: str
    item_name: str
    item_cost: Decimal


class BuyDecisionResponse(BaseModel):
    budget_exists: bool = True
    category: str
    item_cost: float
    remaining_budget_before: Optional[float]
    remaining_budget_after: Optional[float]
    would_exceed_budget: Optional[bool]
    message: str


class CoachResponse(BaseModel):
    advice: str


class ChatMessage(BaseModel):
    role: str  # "user" | "model"
    content: str


class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class CoachChatRequest(InputModel):
    message: str


class LoggedExpense(BaseModel):
    id: int
    amount: float
    category: str
    date: date
    merchant: Optional[str] = None
    note: Optional[str] = None


class ProposedExpense(BaseModel):
    id: str
    amount: float
    category: str
    date: date
    merchant: Optional[str] = None
    note: Optional[str] = None


class CoachChatResponse(BaseModel):
    proposed_expenses: list[ProposedExpense] = Field(default_factory=list)
    reply: str
    logged_expenses: list[LoggedExpense] = []


class AnomalyItem(BaseModel):
    category: str
    type: str
    message: str


class SavingsGoalRequest(InputModel):
    target_amount: Decimal
    months: int


class SavingsGoalCategoryPlan(BaseModel):
    category: str
    current_monthly_avg: float
    target_monthly: float
    cut_amount: float
    cut_percent: float


class SavingsGoalResponse(BaseModel):
    baseline_note: str
    history_reliable: bool
    history_months: int
    target_amount: float
    months: int
    monthly_savings_needed: float
    current_monthly_income: float
    current_baseline_spend: float
    current_monthly_savings: float
    additional_cut_needed: float
    achievable: bool
    categories: list[SavingsGoalCategoryPlan]
    advice: str


class SubscriptionItem(BaseModel):
    merchant: str
    category: str
    average_amount: float
    occurrences: int
    months_seen: int
    last_charged: date
    message: str


class ParsedTransactionPreview(BaseModel):
    amount: float
    category: str
    merchant: Optional[str] = None
    date: date
    note: Optional[str] = None
    source: str
    frequency: str = "daily"


class SmsIngestRequest(InputModel):
    user_id: int
    raw_text: str


class CommitTransaction(InputModel):
    amount: Decimal
    category: str
    merchant: Optional[str] = None
    date: date
    note: Optional[str] = None
    source: str = "manual"
    frequency: str = "daily"


class CommitIngestRequest(InputModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]{16,64}$")
    user_id: int
    transactions: list[CommitTransaction] = Field(min_length=1, max_length=500)


class CommitIngestResponse(BaseModel):
    inserted: int


class BillCreate(InputModel):
    user_id: int
    name: str
    category: str
    amount: Decimal
    due_day: int
    year: Optional[int] = None
    month: Optional[int] = None


class BillStatus(BaseModel):
    due_date: Optional[date] = None
    id: int
    name: str
    category: str
    amount: float
    due_day: int
    status: str  # "paid" | "due" | "overdue"
    paid_date: Optional[date] = None


class WeeklyDigestCategoryAmount(BaseModel):
    category: str
    amount: float


class WeeklyDigestResponse(BaseModel):
    period_start: date
    period_end: date
    total_this_week: float
    total_last_week: float
    top_categories: list[WeeklyDigestCategoryAmount]
    anomalies: list[AnomalyItem]
    subscriptions: list[SubscriptionItem]
    bills_due_soon: list[BillStatus]
    digest_text: str
