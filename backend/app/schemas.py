from datetime import date as date_type, datetime

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color_hex: str = "#898781"


class CategoryOut(BaseModel):
    id: int
    name: str
    color_hex: str
    is_active: bool
    counts_as_expense: bool
    is_essential: bool

    model_config = {"from_attributes": True}


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    account_type: str = "General"


class AccountOut(BaseModel):
    id: int
    name: str
    account_type: str
    is_active: bool

    model_config = {"from_attributes": True}


class TransactionIn(BaseModel):
    date: date_type
    description: str = Field(min_length=1, max_length=255)
    amount: float
    transaction_type: str  # "Income" | "Expense"
    category: str
    account: str = "Primary"
    notes: Optional[str] = None

    @field_validator("transaction_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in ("Income", "Expense"):
            raise ValueError('transaction_type must be "Income" or "Expense"')
        return v

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive (sign is derived from transaction_type)")
        return v


class TransactionOut(BaseModel):
    transaction_id: str
    date: date_type
    description: str
    amount: float
    transaction_type: str
    category: str
    account: str
    period_key: str
    notes: Optional[str]
    source: str
    sync_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransactionTrashOut(TransactionOut):
    deleted_at: datetime
    can_permanently_delete: bool


class BulkCreateIn(BaseModel):
    transactions: list[TransactionIn] = Field(min_length=1, max_length=200)


class AutocompleteIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    date: Optional[date_type] = None


class AutocompleteOut(BaseModel):
    suggestion: str


class CategorizeIn(BaseModel):
    description: str = Field(min_length=1, max_length=255)


class CategorizeOut(BaseModel):
    category: str


class SuggestViewNameIn(BaseModel):
    category: list[str] = []
    category_exclude: bool = False
    account: list[str] = []
    account_exclude: bool = False
    type: Optional[str] = None
    search: Optional[str] = None
    year: Optional[str] = None
    month: Optional[str] = None


class SuggestViewNameOut(BaseModel):
    name: str


class InsightOut(BaseModel):
    insight: str
    range: str


class CompareRecapIn(BaseModel):
    label_a: str = Field(min_length=1, max_length=60)
    label_b: str = Field(min_length=1, max_length=60)
    date_from_a: date_type
    date_to_a: date_type
    date_from_b: date_type
    date_to_b: date_type


class CompareRecapOut(BaseModel):
    recap: str


class QuickAddIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class QuickAddOut(BaseModel):
    date: date_type
    description: str
    amount: float
    transaction_type: str
    category: str
    account: str


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    thread_id: Optional[int] = None  # None = start a new chat thread


class AskRowOut(BaseModel):
    date: date_type
    description: str
    amount: float
    transaction_type: str
    category: str


class AskOut(BaseModel):
    answer: str
    amount: Optional[float] = None
    count: Optional[int] = None
    category: Optional[str] = None
    transaction_type: Optional[str] = None
    range: str
    thread_id: Optional[int] = None
    duration_sec: Optional[float] = None
    # The actual matching rows behind the answer, IN FULL - lets you see
    # exactly what was found and catch a bad extraction yourself, e.g. the
    # wrong category or date range, instead of only trusting the phrased text.
    rows: list[AskRowOut] = []
    message_id: Optional[int] = None
    # A deterministic heuristic ("high"/"medium"/"low"), never a model-
    # reported self-assessment - see the "confidence_reasons" comment in
    # ask() for why. confidence_reasons lists the concrete, human-readable
    # facts that justify anything less than "high".
    confidence: str = "high"
    confidence_reasons: list[str] = []


class ChatThreadOut(BaseModel):
    id: int
    title: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: int
    question: str
    answer: str
    duration_sec: Optional[float] = None
    feedback: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatFeedbackIn(BaseModel):
    helpful: bool
    note: Optional[str] = Field(default=None, max_length=500)


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: dict


class SavedViewOut(BaseModel):
    id: int
    name: str
    filters: dict
    created_at: datetime


class BudgetIn(BaseModel):
    category: str
    period_key: Optional[str] = None  # None = recurring monthly default
    goal_amount: float


class SavingsGoalIn(BaseModel):
    period_key: Optional[str] = None  # None = recurring monthly default
    goal_amount: float


class ConflictResolution(BaseModel):
    keep: str  # "app" | "sheets" | "both"


class SheetRowValidationError(BaseModel):
    row_number: int
    transaction_id: Optional[str]
    reason: str


class BulkDeleteIn(BaseModel):
    transaction_ids: list[str] = Field(min_length=1)


class ImportRowOut(BaseModel):
    row_key: str
    date: date_type
    description: str
    amount: float
    transaction_type: str
    category_guess: str
    is_duplicate: bool
    duplicate_of: Optional[str] = None


class ImportPreviewOut(BaseModel):
    rows: list[ImportRowOut]
    skipped_rows: int
    detected_columns: dict[str, int]


class ImportRowIn(BaseModel):
    date: date_type
    description: str = Field(min_length=1, max_length=255)
    amount: float
    transaction_type: str
    category: str
    account: str = "Primary"

    @field_validator("transaction_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in ("Income", "Expense"):
            raise ValueError('transaction_type must be "Income" or "Expense"')
        return v

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive (sign is derived from transaction_type)")
        return v


class ImportCommitIn(BaseModel):
    rows: list[ImportRowIn]


class ImportCommitOut(BaseModel):
    created_count: int
    transaction_ids: list[str]
