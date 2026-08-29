from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_session
from app.imports.csv_parser import CsvParseError, parse_csv
from app.models import TransactionSource, TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.schemas import ImportCommitIn, ImportCommitOut, ImportPreviewOut, ImportRowOut

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB is generous for a personal bank-statement CSV


@router.post("/csv/preview", response_model=ImportPreviewOut)
async def preview_csv(file: UploadFile = File(...), session: Session = Depends(get_session)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 5 MB)")

    try:
        result = parse_csv(content)
    except CsvParseError as exc:
        raise HTTPException(400, str(exc))

    tx_repo = TransactionRepository(session)
    out_rows = []
    for row in result.rows:
        dupes = tx_repo.find_duplicates(date=row.date, amount=row.amount, transaction_type=row.transaction_type)
        out_rows.append(ImportRowOut(
            row_key=row.row_key, date=row.date, description=row.description, amount=row.amount,
            transaction_type=row.transaction_type, category_guess=row.category_guess,
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
