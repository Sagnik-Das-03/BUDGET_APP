"""Two-way sync engine: pull() reconciles Sheets -> DB, push() writes DB -> Sheets.
Each phase commits independently so a later-phase failure (e.g. report regeneration
hitting a quota error) never rolls back an already-successful pull or push - the
whole point of spec section 21 ("must not lose user data on API failure")."""
import logging

from sqlalchemy.orm import Session

from app.models import LogLevel
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.sync import SyncRepository
from app.repositories.transactions import TransactionRepository
from app.sheets import mapping
from app.sheets.adapter import GoogleSheetsService
from app.sync import periods as periods_mod
from app.sync import reports as reports_mod
from app.utils import next_transaction_id

logger = logging.getLogger("budget_tracker.sync")

TRANSACTIONS_SHEET = "Transactions"


class SyncSummary(dict):
    """Plain dict subclass just for a friendlier repr in logs/CLI output."""


def _ensure_transactions_sheet(sheets: GoogleSheetsService, spreadsheet_id: str) -> list[list[str]]:
    sheets.ensure_sheet(spreadsheet_id, TRANSACTIONS_SHEET)
    raw_rows = sheets.get_rows(spreadsheet_id, TRANSACTIONS_SHEET)
    if not raw_rows:
        sheets.clear_and_write(spreadsheet_id, TRANSACTIONS_SHEET, [mapping.HEADERS])
        reports_mod.format_transactions_header(sheets, spreadsheet_id)
        return [mapping.HEADERS]
    return raw_rows


def pull(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str,
         raw_rows: list[list[str]]) -> dict:
    tx_repo = TransactionRepository(session)
    cat_repo = CategoryRepository(session)
    acct_repo = AccountRepository(session)
    sync_repo = SyncRepository(session)

    data_rows = raw_rows[1:] if raw_rows else []
    counts = {"created": 0, "updated": 0, "conflict": 0, "unchanged": 0, "errors": 0}
    id_to_row_number: dict[str, int] = {}
    rewrites: dict[int, list[str]] = {}

    for offset, raw in enumerate(data_rows):
        row_number = offset + 2  # header is row 1
        if not any((c or "").strip() for c in raw):
            continue
        parsed, error = mapping.parse_row(row_number, raw)
        if error:
            counts["errors"] += 1
            sync_repo.log(f"Row {row_number}: {error.reason}", LogLevel.warn,
                          {"row": row_number, "transaction_id": error.transaction_id})
            continue

        assigned_id = parsed.transaction_id
        if not assigned_id:
            assigned_id = next_transaction_id(tx_repo.all_transaction_ids(), parsed.date.year)
            rewrites[row_number] = mapping.to_row(
                transaction_id=assigned_id, date=parsed.date, description=parsed.description,
                category=parsed.category, account=parsed.account, amount=parsed.amount,
                transaction_type=parsed.transaction_type, period_key=f"{parsed.date.year:04d}-{parsed.date.month:02d}",
                notes=parsed.notes, deleted=parsed.deleted,
            )
        id_to_row_number[assigned_id] = row_number

        category = cat_repo.add(parsed.category)
        account = acct_repo.get_or_create(parsed.account)
        _, action = tx_repo.upsert_from_sheet(
            transaction_id=assigned_id, date=parsed.date, description=parsed.description,
            amount=parsed.amount, transaction_type=parsed.transaction_type, category=category,
            account=account, notes=parsed.notes, deleted=parsed.deleted, row_hint=row_number,
        )
        counts[action] = counts.get(action, 0) + 1

    session.commit()

    if rewrites:
        sheets.update_rows(spreadsheet_id, TRANSACTIONS_SHEET, rewrites)

    return {"counts": counts, "id_to_row_number": id_to_row_number}


def push(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str,
         id_to_row_number: dict[str, int]) -> dict:
    tx_repo = TransactionRepository(session)
    pending = tx_repo.list_pending_sync()

    updates: dict[int, list[str]] = {}
    appends: list[list[str]] = []
    to_mark_synced: list[str] = []

    for txn in pending:
        row = mapping.to_row(
            transaction_id=txn.transaction_id, date=txn.date, description=txn.description,
            category=txn.category.name, account=txn.account.name, amount=txn.amount,
            transaction_type=txn.transaction_type.value if hasattr(txn.transaction_type, "value") else txn.transaction_type,
            period_key=txn.period_key, notes=txn.notes, deleted=txn.deleted_at is not None,
        )
        row_num = id_to_row_number.get(txn.transaction_id)
        if row_num:
            updates[row_num] = row
        else:
            appends.append(row)
        to_mark_synced.append(txn.transaction_id)

    if updates:
        sheets.update_rows(spreadsheet_id, TRANSACTIONS_SHEET, updates)
    if appends:
        sheets.append_rows(spreadsheet_id, TRANSACTIONS_SHEET, appends)

    for tid in to_mark_synced:
        tx_repo.mark_synced(tid)
    session.commit()

    return {"pushed": len(to_mark_synced), "updated": len(updates), "appended": len(appends)}


def run_sync_cycle(session: Session, sheets: GoogleSheetsService, spreadsheet_id: str) -> SyncSummary:
    sync_repo = SyncRepository(session)
    summary = SyncSummary(pull=None, push=None, periods_discovered=[], reports=None, errors=[])

    try:
        raw_rows = _ensure_transactions_sheet(sheets, spreadsheet_id)
        pull_result = pull(session, sheets, spreadsheet_id, raw_rows)
        summary["pull"] = pull_result["counts"]
    except Exception as e:
        logger.exception("pull phase failed")
        sync_repo.log(f"Pull failed: {e}", LogLevel.error)
        session.commit()
        summary["errors"].append(f"pull: {e}")
        pull_result = {"id_to_row_number": {}}

    try:
        push_result = push(session, sheets, spreadsheet_id, pull_result.get("id_to_row_number", {}))
        summary["push"] = push_result
    except Exception as e:
        logger.exception("push phase failed")
        sync_repo.log(f"Push failed: {e}", LogLevel.error)
        session.commit()
        summary["errors"].append(f"push: {e}")

    try:
        periods_mod.ensure_periods_for_transactions(session)
        discovered = periods_mod.discover_sheet_periods(session, sheets, spreadsheet_id)
        summary["periods_discovered"] = discovered
        session.commit()
    except Exception as e:
        logger.exception("period discovery failed")
        sync_repo.log(f"Period discovery failed: {e}", LogLevel.error)
        session.commit()
        summary["errors"].append(f"periods: {e}")

    try:
        report_result = reports_mod.regenerate_all(session, sheets, spreadsheet_id)
        summary["reports"] = report_result
    except Exception as e:
        logger.exception("report regeneration failed")
        sync_repo.log(f"Report regeneration failed: {e}", LogLevel.error)
        session.commit()
        summary["errors"].append(f"reports: {e}")

    sync_repo.touch_meta(spreadsheet_id, TRANSACTIONS_SHEET)
    level = LogLevel.error if summary["errors"] else LogLevel.info
    sync_repo.log(f"Sync cycle complete: {dict(summary)}", level)
    session.commit()
    return summary
