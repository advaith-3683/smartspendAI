from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class UserCreate(BaseModel):
    name: str
    monthly_income: float


class UserOut(BaseModel):
    id: int
    name: str
    monthly_income: float

    class Config:
        from_attributes = True


class BudgetCreate(BaseModel):
    user_id: int
    category: str
    monthly_limit: float
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


class TransactionCreate(BaseModel):
    user_id: int
    amount: float
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


class BuyDecisionRequest(BaseModel):
    user_id: int
    category: str
    item_name: str
    item_cost: float


class BuyDecisionResponse(BaseModel):
    category: str
    item_cost: float
    remaining_budget_before: float
    remaining_budget_after: float
    would_exceed_budget: bool
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


class CoachChatRequest(BaseModel):
    message: str


class LoggedExpense(BaseModel):
    id: int
    amount: float
    category: str
    date: date
    merchant: Optional[str] = None
    note: Optional[str] = None


class CoachChatResponse(BaseModel):
    reply: str
    logged_expenses: list[LoggedExpense] = []


class AnomalyItem(BaseModel):
    category: str
    type: str
    message: str


class SavingsGoalRequest(BaseModel):
    target_amount: float
    months: int


class SavingsGoalCategoryPlan(BaseModel):
    category: str
    current_monthly_avg: float
    target_monthly: float
    cut_amount: float
    cut_percent: float


class SavingsGoalResponse(BaseModel):
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


class SmsIngestRequest(BaseModel):
    user_id: int
    raw_text: str


class CommitTransaction(BaseModel):
    amount: float
    category: str
    merchant: Optional[str] = None
    date: date
    note: Optional[str] = None
    source: str = "manual"
    frequency: str = "daily"


class CommitIngestRequest(BaseModel):
    user_id: int
    transactions: list[CommitTransaction]


class CommitIngestResponse(BaseModel):
    inserted: int


class BillCreate(BaseModel):
    user_id: int
    name: str
    category: str
    amount: float
    due_day: int
    year: Optional[int] = None
    month: Optional[int] = None


class BillStatus(BaseModel):
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
