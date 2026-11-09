"""Parses an India Post (Department of Posts) "My Transactions" savings
account statement PDF into candidate transactions.

This statement has no drawn table gridlines either (pdfplumber's table
detection finds nothing, same as the Indian Bank format in pdf_parser.py),
but its text doesn't extract in reading order at all: each row's "Dr."/"Cr."
marker, its (possibly two-line-wrapped) remarks, and its "date date amount
balance" line interleave in a fixed but non-visual order, e.g.

    Dr.
    BY CHEQUE
    17-06-2026 17-06-2026 20,000.00 10,790.00
    WITHDRAWAL

(the marker first, then whatever of the remarks precedes the date/amount
line, then the date/amount line itself - sometimes carrying short remarks
inline, like "BY CASH DEPOSIT" - then whatever of the remarks follows). So
rather than parsing line by line like the Indian Bank format, this groups
all lines between one "Dr."/"Cr." marker and the next into one block, picks
the date/amount line out of that block wherever it falls, and treats every
other line in the block - in its original order - as a fragment of the
remarks, however many sides of the date/amount line it's split across.

Reuses csv_parser's ParsedRow/ParseResult shape and category-guessing rules
rather than duplicating them, same as pdf_parser.py.
"""

import io
import re
from datetime import date as date_type, datetime
from typing import Optional

from app.imports.csv_parser import ParseResult, ParsedRow, _clean_description, _guess_category

_TYPE_LINE_RE = re.compile(r"^(Dr|Cr)\.$")

# "<date> <date> [remarks] <amount> <balance>" - the two dates are always
# identical (Transaction Date/Value Date) so only the first is kept; the
# middle group is non-greedy so it only captures real inline remarks text
# (e.g. "BY CASH DEPOSIT"), landing empty when the row has none.
_DATE_AMOUNT_RE = re.compile(
    r"^(\d{2}-\d{2}-\d{4})\s+\d{2}-\d{2}-\d{4}\s+(.*?)\s*([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$"
)


class PostParseError(Exception):
    pass


def _extract_text(content: bytes) -> str:
    import pdfplumber  # heavy import (pulls in pypdfium2/Pillow) - deferred to actual use

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise PostParseError(f"Could not read this PDF: {exc}") from exc


def parse_post_pdf(content: bytes) -> ParseResult:
    text = _extract_text(content)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # One block per transaction: everything from a "Dr."/"Cr." marker up to
    # (not including) the next one. Lines before the first marker - the
    # search-criteria preamble and the garbled multi-line column header -
    # belong to no block and are dropped automatically.
    blocks: list[tuple[str, list[str]]] = []
    current_type: Optional[str] = None
    current_lines: list[str] = []
    for line in lines:
        marker = _TYPE_LINE_RE.match(line)
        if marker:
            if current_type is not None:
                blocks.append((current_type, current_lines))
            current_type, current_lines = marker.group(1), []
        elif current_type is not None:
            current_lines.append(line)
    if current_type is not None:
        blocks.append((current_type, current_lines))

    rows: list[ParsedRow] = []
    skipped = 0
    n = 0
    for type_code, block_lines in blocks:
        date_val: Optional[date_type] = None
        amount: Optional[float] = None
        desc_parts: list[str] = []
        for line in block_lines:
            m = _DATE_AMOUNT_RE.match(line)
            if m:
                try:
                    date_val = datetime.strptime(m.group(1), "%d-%m-%Y").date()
                except ValueError:
                    date_val = None
                if m.group(2):
                    desc_parts.append(m.group(2))
                amount = float(m.group(3).replace(",", ""))
            else:
                desc_parts.append(line)

        description = _clean_description(" ".join(desc_parts))
        txn_type = "Expense" if type_code == "Dr" else "Income"
        if date_val is None or amount is None or amount <= 0 or not description:
            skipped += 1
            continue
        rows.append(ParsedRow(
            row_key=f"post-row-{n}", date=date_val, description=description,
            amount=round(amount, 2), transaction_type=txn_type,
            category_guess=_guess_category(description, txn_type),
        ))
        n += 1

    if not rows and not skipped:
        raise PostParseError(
            "Could not find any dated transaction rows in this PDF. "
            "This statement format isn't recognized yet."
        )

    return ParseResult(
        rows=rows, skipped_rows=skipped,
        detected_columns={"date": 0, "description": 1, "amount": 2},
    )
