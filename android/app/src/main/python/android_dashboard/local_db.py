"""Local SQLite mirror of each user's parsed Sheet data, refreshed on a
timer (see server.py's background refresh loop) instead of re-fetched from
Google Sheets on every request. Two problems this solves over the previous
in-memory, per-process TTL cache: (1) filtering/browsing transactions no
longer risks a live Sheets round-trip on every keystroke, and (2) the last
good data survives an app/service restart instead of starting empty and
waiting on Sheets again. Still entirely read-only from the app's own
perspective - nothing here ever writes back to Sheets, it only mirrors
what Sheets already has.

Stdlib-only (sqlite3), matching the rest of this package's zero-extra-
dependency approach - Chaquopy bundles sqlite3 with its CPython build."""
import json
import sqlite3
import threading
import time
from dataclasses import asdict
from datetime import date as date_type
from pathlib import Path
from typing import Optional

from android_dashboard.parsing import BudgetGoal, CategoryMeta, Config, Txn

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    user_name TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    account TEXT NOT NULL,
    amount REAL NOT NULL,
    transaction_type TEXT NOT NULL,
    notes TEXT,
    deleted INTEGER NOT NULL,
    PRIMARY KEY (user_name, transaction_id)
);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions (user_name, date);
CREATE TABLE IF NOT EXISTS config_cache (
    user_name TEXT PRIMARY KEY,
    config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refreshed_at (
    user_name TEXT PRIMARY KEY,
    ts REAL NOT NULL
);
"""


def _config_to_dict(config: Config) -> dict:
    return {
        "categories": {name: asdict(meta) for name, meta in config.categories.items()},
        "budgets": [asdict(b) for b in config.budgets],
        "savings_goals": [asdict(g) for g in config.savings_goals],
    }


def _config_from_dict(data: dict) -> Config:
    return Config(
        categories={name: CategoryMeta(**meta) for name, meta in data.get("categories", {}).items()},
        budgets=[BudgetGoal(**b) for b in data.get("budgets", [])],
        savings_goals=[BudgetGoal(**g) for g in data.get("savings_goals", [])],
    )


class LocalStore:
    """One SQLite file, one row per (user, transaction) plus one config/
    refresh-timestamp row per user. A single `threading.Lock` serializes
    writes (the background refresh thread is the only writer; reads from
    request-handling threads use their own short-lived connections and
    never block on it)."""

    def __init__(self, db_path: Path):
        self._path = db_path
        self._write_lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, check_same_thread=False)

    def save(self, user_name: str, txns: list[Txn], config: Config) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute("DELETE FROM transactions WHERE user_name = ?", (user_name,))
            conn.executemany(
                "INSERT INTO transactions (user_name, transaction_id, date, description, category, "
                "account, amount, transaction_type, notes, deleted) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (user_name, t.transaction_id, t.date.isoformat(), t.description, t.category,
                     t.account, t.amount, t.transaction_type, t.notes, int(t.deleted))
                    for t in txns
                ],
            )
            conn.execute(
                "INSERT INTO config_cache (user_name, config_json) VALUES (?, ?) "
                "ON CONFLICT(user_name) DO UPDATE SET config_json = excluded.config_json",
                (user_name, json.dumps(_config_to_dict(config))),
            )
            conn.execute(
                "INSERT INTO refreshed_at (user_name, ts) VALUES (?, ?) "
                "ON CONFLICT(user_name) DO UPDATE SET ts = excluded.ts",
                (user_name, time.time()),
            )
            conn.commit()

    def load(self, user_name: str) -> Optional[tuple[list[Txn], Config, float]]:
        """None if this user has never been successfully refreshed yet."""
        with self._connect() as conn:
            ts_row = conn.execute("SELECT ts FROM refreshed_at WHERE user_name = ?", (user_name,)).fetchone()
            if ts_row is None:
                return None
            txn_rows = conn.execute(
                "SELECT transaction_id, date, description, category, account, amount, "
                "transaction_type, notes, deleted FROM transactions WHERE user_name = ? "
                "ORDER BY date DESC, rowid DESC",
                (user_name,),
            ).fetchall()
            cfg_row = conn.execute(
                "SELECT config_json FROM config_cache WHERE user_name = ?", (user_name,),
            ).fetchone()

        txns = [
            Txn(
                transaction_id=r[0], date=date_type.fromisoformat(r[1]), description=r[2], category=r[3],
                account=r[4], amount=r[5], transaction_type=r[6], notes=r[7], deleted=bool(r[8]),
            )
            for r in txn_rows
        ]
        config = _config_from_dict(json.loads(cfg_row[0])) if cfg_row else Config()
        return txns, config, ts_row[0]
