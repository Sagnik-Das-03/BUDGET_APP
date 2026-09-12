import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_session
from app.imports.csv_parser import CsvParseError, parse_csv
from app.llm.router import llm_router
from app.models import TransactionSource, TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.schemas import ImportCommitIn, ImportCommitOut, ImportPreviewOut, ImportRowOut

router = APIRouter(prefix="/api/imports", tags=["imports"])
logger = logging.getLogger("budget_tracker.imports")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB is generous for a personal bank-statement CSV

# How many low-confidence descriptions go into one LLM call - a personal
# bank statement's "regex couldn't place this" rows are usually a small
# minority, and keeping each call's prompt/output modest keeps a small
# quantized model reliable; import latency isn't a concern worth trading
# accuracy for here, so there's no cap on how many BATCHES a preview runs.
LLM_CATEGORIZE_BATCH_SIZE = 20


def _llm_categorize_batch(descriptions: list[str], categories: list[str]) -> Optional[list[Optional[str]]]:
    """Best-effort batched categorization for descriptions the regex rules in
    csv_parser.py couldn't confidently place (fell back to "Other") and that
    don't already match a prior transaction's category either. Returns None
    (caller keeps each row's existing "Other" guess) if the model is
    unavailable or the call fails outright - a missed AI guess during import
    is never worse than the harmless default it would have replaced, but a
    raised exception here must never break the whole import. A per-row None
    inside the returned list means that one row's guess didn't land (wrong
    length would be a whole-batch failure instead - see the length check)."""
    if not llm_router.available or not categories:
        return None
    schema = {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": categories},
                "minItems": len(descriptions),
                "maxItems": len(descriptions),
            },
        },
        "required": ["categories"],
        "additionalProperties": False,
    }
    numbered = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
    prompt = (
        f"Transactions:\n{numbered}\n\n"
        f"Assign each of the {len(descriptions)} transactions above, in the same order, "
        "its single best-matching category."
    )
    try:
        result = llm_router.complete_json(
            "categorize", prompt,
            system_message="You categorize personal-finance transactions into one of a fixed set of categories.",
            schema=schema,
            max_output_tokens=20 * len(descriptions) + 20,
        )
        guesses = result.get("categories")
        if not isinstance(guesses, list) or len(guesses) != len(descriptions):
            logger.warning("Batch LLM categorization returned %d guesses for %d rows - discarding",
                            len(guesses) if isinstance(guesses, list) else 0, len(descriptions))
            return None
        return [g if g in categories else None for g in guesses]
    except Exception:
        logger.exception("Batch LLM categorization failed for %d rows - keeping regex guesses", len(descriptions))
        return None


@router.post("/csv/preview", response_model=ImportPreviewOut)
def preview_csv(file: UploadFile = File(...), session: Session = Depends(get_session)):
    # Sync def, not async - FastAPI runs this in its threadpool instead of
    # the event loop, since batched LLM calls below can take a real while and
    # must not block every other request in the meantime (`file.file.read()`
    # is UploadFile's underlying sync file object; `await file.read()` isn't
    # available outside an async def).
    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 5 MB)")

    try:
        result = parse_csv(content)
    except CsvParseError as exc:
        raise HTTPException(400, str(exc))

    tx_repo = TransactionRepository(session)

    # Three tiers, cheapest/most-confident first:
    #   1. A prior transaction with this exact description already tells us
    #      its real category - more reliable than any guess, and free.
    #   2. The regex rules in csv_parser.py found a confident match (anything
    #      but the "Other" catch-all, which just means no rule fired).
    #   3. Neither - batched through the local LLM, since a wrong "Other"
    #      default is worth spending real time to improve during import.
    guesses: list[str] = []
    unresolved: list[int] = []
    for row in result.rows:
        exact = tx_repo.category_for_description(row.description)
        guesses.append(exact or row.category_guess)
        if not exact and row.category_guess == "Other":
            unresolved.append(len(guesses) - 1)

    if unresolved:
        # "Income" is excluded here: these rows are already known Expense-type
        # (income rows always resolve to the literal "Income" guess up front
        # and never reach this tier - see csv_parser._guess_category), so
        # offering it as a pickable category just invites the model to
        # mislabel an expense as income. Mirrors the regex rules' own
        # Income/Expense split, which never lets a pattern match into Income.
        categories = [c.name for c in CategoryRepository(session).list() if c.name != "Income"]
        for start in range(0, len(unresolved), LLM_CATEGORIZE_BATCH_SIZE):
            batch_indices = unresolved[start:start + LLM_CATEGORIZE_BATCH_SIZE]
            batch_guesses = _llm_categorize_batch([result.rows[i].description for i in batch_indices], categories)
            if batch_guesses is None:
                continue  # keep "Other" for this whole batch
            for idx, guess in zip(batch_indices, batch_guesses):
                if guess:
                    guesses[idx] = guess

    out_rows = []
    for row, category_guess in zip(result.rows, guesses):
        dupes = tx_repo.find_duplicates(date=row.date, amount=row.amount, transaction_type=row.transaction_type)
        out_rows.append(ImportRowOut(
            row_key=row.row_key, date=row.date, description=row.description, amount=row.amount,
            transaction_type=row.transaction_type, category_guess=category_guess,
            is_duplicate=bool(dupes), duplicate_of=dupes[0].transaction_id if dupes else None,
        ))

    return ImportPreviewOut(rows=out_rows, skipped_rows=result.skipped_rows, detected_columns=result.detected_columns)


@router.post("/csv/commit", response_model=ImportCommitOut)
def commit_csv(payload: ImportCommitIn, session: Session = Depends(get_session)):
    if not payload.rows:
        raise HTTPException(400, "No rows to import")

    cat_repo = CategoryRepository(session)
    acct_repo = AccountRepository(session)
    tx_repo = TransactionRepository(session)

    created_ids = []
    for row in payload.rows:
        category = cat_repo.add(row.category)
        account = acct_repo.get_or_create(row.account)
        txn = tx_repo.create(
            date=row.date, description=row.description, amount=row.amount,
            transaction_type=TransactionType(row.transaction_type), category=category, account=account,
            source=TransactionSource.legacy_import,
        )
        created_ids.append(txn.transaction_id)

    session.commit()
    return ImportCommitOut(created_count=len(created_ids), transaction_ids=created_ids)
