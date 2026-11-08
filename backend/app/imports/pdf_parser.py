"""Parses an Indian Bank "Account Statement" PDF into candidate transactions.

Built against a real exported statement: a tabular Date / Transaction Details /
Debits / Credits / Balance layout with NO drawn grid lines (so pdfplumber's own
table detection finds nothing - this parses the extracted text directly), a
narration that commonly wraps across several lines (and sometimes across a page
break) before the next dated row begins, and a repeated table header plus an
"Ending Balance" / "Total" footer on every page that must be recognized and
skipped rather than swallowed into the previous row's description.

Reuses csv_parser's ParsedRow/ParseResult shape and category-guessing rules
rather than duplicating them, so a PDF-sourced row gets identical treatment
(exact-match lookup, regex rules, LLM fallback) to a CSV-sourced one in
app/api/imports.py's shared preview/commit pipeline.
"""

import io
import re
from datetime import date as date_type, datetime
from typing import Optional

from app.imports.csv_parser import ParseResult, ParsedRow, _clean_description, _guess_category

# "18 Jun 2026 <rest of the first line>" - the ONLY place a date appears is at
# the start of a transaction's first line; every wrapped continuation line
# has no date at all, which is exactly how a new transaction is told apart
# from more of the previous one's narration.
_DATE_LINE_RE = re.compile(r"^(\d{1,2} [A-Za-z]{3} \d{4})\s+(.*)$")

# The trailing Debits/Credits/Balance cells on a transaction's first line -
# each is either a bare "-" (empty cell) or "INR 1,234.56". Matched from the
# END of the line (re.search, not match, with $) so whatever precedes them,
# however it reads, is the first line of the description - this is also what
# keeps an embedded hyphen in the narration itself (e.g. "TRAN DATE -(MMDD)")
# from being mistaken for an empty cell: it has no whitespace on both sides.
_CELLS_RE = re.compile(
    r"^(.*?)\s+(-|INR\s[\d,]+\.\d{2})\s+(-|INR\s[\d,]+\.\d{2})\s+(INR\s[\d,]+\.\d{2})$"
)

# The repeated table header and the per-page footer ("Indian Bank | | 1/2")
# are page-boundary noise, not transaction content, but narration can
# legitimately CONTINUE right after them on the next page - so these are
# skipped without disturbing whatever transaction is still accumulating.
_PAGE_BOUNDARY_RE = re.compile(r"^(Date\s+Transaction Details|Indian Bank\s*\|)", re.IGNORECASE)

# "Ending Balance"/"Total" only appear once, after the very last transaction -
# real terminators, so these DO flush and end whatever was accumulating.
_FOOTER_RE = re.compile(r"^(Ending Balance|Total\s+INR)", re.IGNORECASE)

_AMOUNT_RE = re.compile(r"[\d,]+\.\d{2}")


class PdfParseError(Exception):
    pass


def _parse_cell_amount(cell: str) -> Optional[float]:
    if cell.strip() == "-":
        return None
    m = _AMOUNT_RE.search(cell)
    return float(m.group(0).replace(",", "")) if m else None


def _extract_text(content: bytes) -> str:
    import pdfplumber  # heavy import (pulls in pypdfium2/Pillow) - deferred to actual use

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise PdfParseError(f"Could not read this PDF: {exc}") from exc


def parse_pdf(content: bytes) -> ParseResult:
    text = _extract_text(content)

    rows: list[ParsedRow] = []
    skipped = 0
    n = 0

    # Accumulator for whatever transaction is currently being built up across
    # possibly several wrapped lines (and possibly a page break) - flushed to
    # `rows` the moment the NEXT dated line or a noise line is seen, or at
    # end of document.
    pending_date: Optional[date_type] = None
    pending_debit_cell: Optional[str] = None
    pending_credit_cell: Optional[str] = None
    pending_desc_parts: list[str] = []

    def flush():
        nonlocal n, skipped
        if pending_date is None:
            return
        description = _clean_description("".join(pending_desc_parts))
        debit = _parse_cell_amount(pending_debit_cell) if pending_debit_cell is not None else None
        credit = _parse_cell_amount(pending_credit_cell) if pending_credit_cell is not None else None
        amount, txn_type = (debit, "Expense") if debit is not None else (credit, "Income")
        if not description or amount is None or amount <= 0:
            skipped += 1
            return
        rows.append(ParsedRow(
            row_key=f"pdf-row-{n}", date=pending_date, description=description,
            amount=round(amount, 2), transaction_type=txn_type,
            category_guess=_guess_category(description, txn_type),
        ))
        n += 1

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        date_match = _DATE_LINE_RE.match(line)
        if date_match:
            flush()
            pending_desc_parts = []
            pending_debit_cell = pending_credit_cell = None
            try:
                pending_date = datetime.strptime(date_match.group(1), "%d %b %Y").date()
            except ValueError:
                pending_date = None
                continue

            cells_match = _CELLS_RE.match(date_match.group(2))
            if cells_match:
                pending_desc_parts.append(cells_match.group(1))
                pending_debit_cell, pending_credit_cell = cells_match.group(2), cells_match.group(3)
            else:
                # Debits/Credits/Balance didn't all land on this first line
                # (seen with a long first narration line in practice) - keep
                # the whole remainder as description text and let the real
                # amounts turn up contributed by _CELLS_RE on a later line's
                # own match attempt... in practice this hasn't been observed,
                # so treat it as plain continuation text for now.
                pending_desc_parts.append(date_match.group(2))
            continue

        if _PAGE_BOUNDARY_RE.match(line):
            continue

        if _FOOTER_RE.match(line):
            flush()
            pending_date = None
            continue

        if pending_date is not None:
            pending_desc_parts.append(line)
        # Lines before the first transaction (account/branch preamble) are
        # silently ignored - there's no pending transaction yet to append to.

    flush()

    if not rows and not skipped:
        raise PdfParseError(
            "Could not find any dated transaction rows in this PDF. "
            "This statement format isn't recognized yet."
        )

    return ParseResult(
        rows=rows, skipped_rows=skipped,
        detected_columns={"date": 0, "description": 1, "debit": 2, "credit": 3},
    )
