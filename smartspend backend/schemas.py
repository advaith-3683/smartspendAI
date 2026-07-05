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


class AnomalyItem(BaseModel):
    category: str
    type: str
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
