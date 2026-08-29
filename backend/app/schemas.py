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


class BudgetIn(BaseModel):
    category: str
    period_key: Optional[str] = None  # None = recurring monthly default
    goal_amount: float


class SavingsGoalIn(BaseModel):
    period_key: Optional[str] = None  # None = recurring monthly default
    goal_amount: float


class ConflictResolution(BaseModel):
    keep: str  # "app" | "sheets"


class SheetRowValidationError(BaseModel):
    row_number: int
    transaction_id: Optional[str]
    reason: str
