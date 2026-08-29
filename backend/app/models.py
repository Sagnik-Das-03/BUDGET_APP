import enum
from datetime import date as date_type, datetime

from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TransactionType(str, enum.Enum):
    income = "Income"
    expense = "Expense"


class TransactionSource(str, enum.Enum):
    app = "app"
    google_sheets = "google_sheets"
    legacy_import = "legacy_import"


class SyncStatus(str, enum.Enum):
    pending = "pending"
    synced = "synced"
    conflict = "conflict"
    error = "error"


class LogLevel(str, enum.Enum):
    info = "info"
    warn = "warn"
    error = "error"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), default="#898781")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # False for categories that are savings/investment/transfers rather than true
    # consumption (SIP, Savings) - excluded from the Expenses/Net Savings KPI so
    # "Net Savings" reflects money not consumed, not just cash sitting idle.
    counts_as_expense: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), default="General")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class MonthlyPeriod(Base):
    __tablename__ = "monthly_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_key: Mapped[str] = mapped_column(String(7), unique=True, nullable=False)  # "2026-04"
    label: Mapped[str] = mapped_column(String(32), nullable=False)  # "April 2026"
    sheet_gid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    discovered_from_sheet: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("category_id", "period_key", name="uq_budget_category_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    period_key: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # None = recurring monthly default
    goal_amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    category: Mapped["Category"] = relationship()


class SavingsGoal(Base):
    """A goal on Net Savings (Income - true Expenses) itself, not tied to any one
    category - distinct from Budget, which caps spend per category."""
    __tablename__ = "savings_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_key: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # None = recurring monthly default
    goal_amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppSetting(Base):
    """Generic runtime-editable key/value store - e.g. a sync interval override
    from the UI - that takes effect immediately and survives restarts, unlike
    .env (which needs a restart to pick up). Not for secrets - those stay in .env."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    period_key: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-04", derived from date
    raw_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # original text, audit trail
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped[TransactionSource] = mapped_column(Enum(TransactionSource), default=TransactionSource.app)
    row_hint: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # last known sheet row, perf hint only
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_synced_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    conflict_sheet_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON, set only on conflict
    sync_status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.pending, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    category: Mapped["Category"] = relationship(back_populates="transactions")
    account: Mapped["Account"] = relationship(back_populates="transactions")


class SyncMeta(Base):
    __tablename__ = "sync_meta"
    __table_args__ = (UniqueConstraint("spreadsheet_id", "sheet_name", name="uq_sync_meta_sheet"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spreadsheet_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_gid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_row_count: Mapped[int] = mapped_column(Integer, default=0)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    level: Mapped[LogLevel] = mapped_column(Enum(LogLevel), default=LogLevel.info)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob
