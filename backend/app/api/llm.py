import re
from datetime import date as date_type, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dashboard import _resolve_range as _dashboard_resolve_range
from app.dashboard import calculations as calc
from app.db import get_session
from app.llm.config import MODEL_DISPLAY_NAMES, TASK_MODEL
from app.llm.router import llm_router
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.schemas import (
    AskIn, AskOut, AutocompleteIn, AutocompleteOut, CategorizeIn, CategorizeOut,
    CompareRecapIn, CompareRecapOut, QuickAddIn, QuickAddOut, RecapOut,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

# Matches a trailing "(DD/MM/YY)"-style date this user's descriptions often
# embed, e.g. "Zomato (28/08/26)" - a past description is a great style
# template, but its own baked-in date is almost always stale for a NEW
# transaction being entered today (or on whatever date is currently picked).
_TRAILING_DATE = re.compile(r"\(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\)\s*$")


def _refresh_trailing_date(text: str, new_date: Optional[date_type]) -> str:
    if not new_date:
        return text
    return _TRAILING_DATE.sub(f"({new_date.day:02d}/{new_date.month:02d}/{new_date.strftime('%y')})", text)


_RANGE_LABELS = {
    "this_week": "this week", "this_month": "this month", "last_month": "last month",
    "this_year": "this year", "all_time": "all time",
}


def _resolve_named_range(range_key: str, date_from: Optional[date_type] = None,
                          date_to: Optional[date_type] = None) -> tuple[Optional[date_type], Optional[date_type]]:
    """this_week/this_month/this_year/all_time/custom go through the dashboard's
    own resolver (single source of truth for what those mean); last_month is
    an addition dashboard doesn't need but chat/recap questions often do."""
    if range_key == "last_month":
        return calc._range_previous_month(calc.range_this_month()[0])
    return _dashboard_resolve_range(range_key, date_from, date_to)


@router.get("/status")
def llm_status():
    return {
        "available": llm_router.available,
        "reason": llm_router.unavailable_reason,
        "models": {task: MODEL_DISPLAY_NAMES.get(model_key, model_key) for task, model_key in TASK_MODEL.items()},
    }


@router.post("/autocomplete", response_model=AutocompleteOut)
def autocomplete(payload: AutocompleteIn, session: Session = Depends(get_session)):
    text = payload.text.strip()
    if not text:
        return AutocompleteOut(suggestion="")

    seen: list[str] = []
    for desc in TransactionRepository(session).recent_descriptions(limit=300):
        if desc not in seen:
            seen.append(desc)
        if len(seen) >= 200:
            break

    # A past description sharing this prefix is a better bet than any LLM guess.
    prefix_matches = [d for d in seen if d.lower() != text.lower() and d.lower().startswith(text.lower())]
    if prefix_matches:
        return AutocompleteOut(suggestion=_refresh_trailing_date(prefix_matches[0], payload.date))

    if not llm_router.available or len(text) < 2:
        return AutocompleteOut(suggestion="")

    examples = "\n".join(f"- {d}" for d in seen[:20])
    prompt = (
        f"Past transaction descriptions from this user (most recent first):\n{examples}\n\n"
        f'Complete this partial transaction description in the same style: "{text}"\n'
        "Reply with ONLY the completed description, nothing else."
    )
    try:
        suggestion = llm_router.complete(
            "autocomplete", prompt,
            system_message="You autocomplete short transaction descriptions for a personal budget tracker app. Be concise.",
            max_output_tokens=24,
        )
    except Exception:
        return AutocompleteOut(suggestion="")

    suggestion = suggestion.strip().strip('"')
    if not suggestion or suggestion.lower() == text.lower() or not suggestion.lower().startswith(text.lower()):
        return AutocompleteOut(suggestion="")
    return AutocompleteOut(suggestion=_refresh_trailing_date(suggestion, payload.date))


@router.post("/categorize", response_model=CategorizeOut)
def categorize(payload: CategorizeIn, session: Session = Depends(get_session)):
    description = payload.description.strip()
    if not description:
        return CategorizeOut(category="")

    # A prior transaction with this exact description already tells us the
    # right category - more reliable than any model guess, and free.
    existing = TransactionRepository(session).category_for_description(description)
    if existing:
        return CategorizeOut(category=existing)

    categories = [c.name for c in CategoryRepository(session).list()]
    if not llm_router.available or not categories:
        return CategorizeOut(category="")

    schema = {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": categories}},
        "required": ["category"],
        "additionalProperties": False,
    }
    try:
        result = llm_router.complete_json(
            "categorize",
            f'Transaction description: "{description}"\nPick the single best matching category for it.',
            system_message="You categorize personal-finance transactions into one of a fixed set of categories.",
            schema=schema,
            max_output_tokens=40,
        )
        category = result.get("category", "")
    except Exception:
        category = ""
    # The enum constraint should guarantee this, but never trust it blindly.
    return CategorizeOut(category=category if category in categories else "")


_QUICK_ADD_AMOUNT = re.compile(r"(?:rs\.?|inr|₹)?\s?\d[\d,]*(?:\.\d+)?", re.IGNORECASE)
_QUICK_ADD_DATE_WORDS = re.compile(
    r"\b(today|yesterday|tomorrow|day before yesterday|on\s+the\s+\d{1,2}(?:st|nd|rd|th)?|"
    r"the\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:st|nd|rd|th)?)\b", re.IGNORECASE,
)
_QUICK_ADD_FILLER_WORDS = re.compile(r"\b(spent|paid|got|received|for|on|of|a|an)\b", re.IGNORECASE)


def _extract_quick_add_description(raw_text: str) -> str:
    """Derives the description from the user's own words via plain string
    manipulation rather than asking the model to echo it back - constrained
    JSON decoding proved reliable for the enum/numeric fields below, but
    testing showed it hallucinating this one free-text field outright (e.g.
    "Zomato 250 today" came back with description "Anda") even with the
    schema and prompt both saying to copy it verbatim."""
    # Date words first: an ordinal like "2nd" would otherwise have its leading
    # digit eaten by the amount pattern, leaving a stray "nd" behind.
    cleaned = _QUICK_ADD_DATE_WORDS.sub(" ", raw_text)
    cleaned = _QUICK_ADD_AMOUNT.sub(" ", cleaned)
    cleaned = _QUICK_ADD_FILLER_WORDS.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned or raw_text.strip()


@router.post("/quick_add", response_model=QuickAddOut)
def quick_add(payload: QuickAddIn, session: Session = Depends(get_session)):
    """Parses a one-line description like 'Zomato 250 today' or 'got salary
    87000 yesterday' into a draft transaction for the user to review before
    saving - never creates anything itself. days_ago (a small integer) is
    used instead of asking the model for an absolute date, since that's a
    much safer thing for it to get right than date arithmetic; description is
    derived in Python (see _extract_quick_add_description), not the model."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "Empty input")
    if not llm_router.available:
        raise HTTPException(503, "AI features are not available")

    categories = [c.name for c in CategoryRepository(session).list()]
    if not categories:
        raise HTTPException(503, "No categories configured")

    schema = {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "exclusiveMinimum": 0},
            "transaction_type": {"type": "string", "enum": ["Income", "Expense"]},
            "category": {"type": "string", "enum": categories},
            "days_ago": {"type": "integer", "minimum": 0, "maximum": 365},
        },
        "required": ["amount", "transaction_type", "category", "days_ago"],
        "additionalProperties": False,
    }
    system_message = (
        "You extract the structured details of a single financial transaction from a short user message.\n"
        f"Available categories: {', '.join(categories)} - pick the closest match.\n"
        '"days_ago": how many days before today this happened - 0 for today/unspecified, 1 for yesterday, etc.\n'
        '"transaction_type": "Income" if money was received, otherwise "Expense".'
    )
    prompt = f'Today: {date_type.today().isoformat()}\nUser input: "{text}"\nExtract this as a transaction.'
    try:
        parsed = llm_router.complete_json(
            "quick_add", prompt, system_message=system_message, schema=schema, max_output_tokens=40,
        )
    except Exception as e:
        raise HTTPException(503, f"Couldn't understand that ({e})") from e

    amount = float(parsed.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(422, "Couldn't figure out an amount from that - try including a number")

    category = parsed.get("category")
    if category not in categories:
        category = "Other" if "Other" in categories else categories[0]
    ttype = parsed.get("transaction_type")
    if ttype not in ("Income", "Expense"):
        ttype = "Expense"
    days_ago = max(0, min(365, int(parsed.get("days_ago") or 0)))

    return QuickAddOut(
        date=date_type.today() - timedelta(days=days_ago), description=_extract_quick_add_description(text),
        amount=round(amount, 2), transaction_type=ttype, category=category, account="Primary",
    )


@router.get("/recap", response_model=RecapOut)
def recap(range: str = "this_month", date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
          label: Optional[str] = None, session: Session = Depends(get_session)):
    """Recap for whichever range/period the caller is currently looking at -
    range is one of _RANGE_LABELS' keys, or "custom" with date_from/date_to
    (e.g. a drilled-into month on the Dashboard). `label` is an optional
    human-readable description of a custom range for the prompt (falls back
    to the raw dates)."""
    if not llm_router.available:
        raise HTTPException(503, "AI features are not available")

    d_from, d_to = _resolve_named_range(range, date_from, date_to)
    totals = calc.totals(session, d_from, d_to)
    top_categories = calc.by_category(session, d_from, d_to, transaction_type="Expense")[:8]

    if not top_categories and not totals["income"]:
        return RecapOut(recap="Not enough data yet to generate a recap for this period.", range=range)

    period_desc = label or _RANGE_LABELS.get(range) or (f"{d_from} to {d_to}" if d_from and d_to else "all time")
    category_lines = "\n".join(f"- {c['category']}: Rs {c['total']:,.0f}" for c in top_categories) or "- (none)"
    prompt = (
        f"Period: {period_desc}\n"
        f"Income: Rs {totals['income']:,.0f}\n"
        f"Expenses: Rs {totals['expenses']:,.0f}\n"
        f"Net savings: Rs {totals['net']:,.0f}\n"
        f"Savings rate: {totals['savings_rate'] * 100:.1f}%\n"
        f"Top expense categories:\n{category_lines}\n\n"
        "Write a short, friendly 3-4 sentence recap of this period's finances for the user. "
        "Mention anything notable (a dominant category, a good or concerning savings rate). "
        "Be specific with the numbers given above - do not invent new ones."
    )
    try:
        recap_text = llm_router.complete(
            "summarize", prompt,
            system_message="You are a friendly personal-finance assistant writing a short spending recap.",
            max_output_tokens=220,
        )
    except Exception as e:
        raise HTTPException(503, f"Failed to generate recap: {e}") from e

    return RecapOut(recap=recap_text or "Not enough data yet to generate a recap for this period.", range=range)


@router.post("/compare_recap", response_model=CompareRecapOut)
def compare_recap(payload: CompareRecapIn, session: Session = Depends(get_session)):
    if not llm_router.available:
        raise HTTPException(503, "AI features are not available")

    totals_a = calc.totals(session, payload.date_from_a, payload.date_to_a)
    totals_b = calc.totals(session, payload.date_from_b, payload.date_to_b)
    cats_a = {c["category"]: c["total"] for c in calc.by_category(
        session, payload.date_from_a, payload.date_to_a, transaction_type="Expense")}
    cats_b = {c["category"]: c["total"] for c in calc.by_category(
        session, payload.date_from_b, payload.date_to_b, transaction_type="Expense")}
    names = sorted(set(cats_a) | set(cats_b), key=lambda n: -(cats_a.get(n, 0) + cats_b.get(n, 0)))[:8]
    category_lines = "\n".join(
        f"- {n}: {payload.label_a}=Rs {cats_a.get(n, 0):,.0f}, {payload.label_b}=Rs {cats_b.get(n, 0):,.0f}"
        for n in names
    ) or "- (no expense categories in either period)"

    prompt = (
        f"{payload.label_a}: Income Rs {totals_a['income']:,.0f}, Expenses Rs {totals_a['expenses']:,.0f}, "
        f"Net Rs {totals_a['net']:,.0f}, Savings rate {totals_a['savings_rate'] * 100:.1f}%\n"
        f"{payload.label_b}: Income Rs {totals_b['income']:,.0f}, Expenses Rs {totals_b['expenses']:,.0f}, "
        f"Net Rs {totals_b['net']:,.0f}, Savings rate {totals_b['savings_rate'] * 100:.1f}%\n"
        f"Category breakdown:\n{category_lines}\n\n"
        f"Write a short, friendly 3-4 sentence comparison of {payload.label_a} vs {payload.label_b}. "
        "Call out the most notable changes (biggest category swing, income or savings-rate change). "
        "Be specific with the numbers given above - do not invent new ones."
    )
    try:
        recap_text = llm_router.complete(
            "summarize", prompt,
            system_message="You are a friendly personal-finance assistant comparing two time periods.",
            max_output_tokens=220,
        )
    except Exception as e:
        raise HTTPException(503, f"Failed to generate comparison: {e}") from e

    return CompareRecapOut(recap=recap_text or "Not enough data to compare these periods.")


@router.post("/ask", response_model=AskOut)
def ask(payload: AskIn, session: Session = Depends(get_session)):
    question = payload.question.strip()
    if not llm_router.available:
        return AskOut(answer="AI features aren't available right now.", range="this_month")

    categories = [c.name for c in CategoryRepository(session).list()]
    schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": [*categories, "ALL"]},
            "transaction_type": {"type": "string", "enum": ["Income", "Expense", "ANY"]},
            "range": {"type": "string", "enum": list(_RANGE_LABELS.keys())},
            "aggregation": {"type": "string", "enum": ["sum", "count", "avg"]},
        },
        "required": ["category", "transaction_type", "range", "aggregation"],
        "additionalProperties": False,
    }
    prompt = (
        f"Today's date: {date_type.today().isoformat()}\n"
        f'User question: "{question}"\n'
        "Extract this spending question as a structured query."
    )
    # The enum constraint only guarantees a VALID category comes back, not a
    # semantically correct one - the model still needs the actual names
    # spelled out in readable text to match "food" to "Food-Order", etc.
    system_message = (
        "You convert a personal-finance question into a structured query.\n"
        f"Available categories: {', '.join(categories)}. Use \"ALL\" if the question doesn't mention one of these.\n"
        'transaction_type: "Income", "Expense", or "ANY" if unspecified.\n'
        'range: "this_week", "this_month", "last_month" (the previous calendar month), "this_year" '
        '(the current calendar year), or "all_time" (no time limit; use this if no time period is mentioned).\n'
        'aggregation: "count" for how-many questions, "avg" for average, otherwise "sum".'
    )
    try:
        parsed = llm_router.complete_json(
            "query_parse", prompt, system_message=system_message, schema=schema, max_output_tokens=60,
        )
    except Exception as e:
        return AskOut(answer=f"Couldn't understand that question ({e}).", range="this_month")

    category = parsed.get("category")
    category = category if category in categories else None
    ttype = parsed.get("transaction_type")
    ttype = ttype if ttype in ("Income", "Expense") else None
    range_key = parsed.get("range") if parsed.get("range") in _RANGE_LABELS else "this_month"
    aggregation = parsed.get("aggregation") if parsed.get("aggregation") in ("sum", "count", "avg") else "sum"

    date_from, date_to = _resolve_named_range(range_key)
    category_ids = None
    if category:
        cat = CategoryRepository(session).get_by_name(category)
        category_ids = [cat.id] if cat else None

    rows = TransactionRepository(session).filter(
        category_ids=category_ids, transaction_type=ttype, date_from=date_from, date_to=date_to,
    )

    if aggregation == "count":
        value = float(len(rows))
    elif aggregation == "avg":
        value = (sum(r.amount for r in rows) / len(rows)) if rows else 0.0
    else:
        value = sum(r.amount for r in rows)

    period_label = _RANGE_LABELS[range_key]
    scope = f"on {category}" if category else "overall"
    type_label = f" ({ttype.lower()})" if ttype else ""

    if aggregation == "count":
        answer = f"You had {int(value)} transaction{'s' if value != 1 else ''} {scope}{type_label} {period_label}."
    elif aggregation == "avg":
        answer = f"Your average transaction {scope}{type_label} {period_label} was Rs {value:,.0f}."
    elif ttype == "Income":
        answer = f"You received Rs {value:,.0f} {scope} {period_label}."
    else:
        answer = f"You spent Rs {value:,.0f} {scope}{type_label} {period_label}."

    return AskOut(
        answer=answer,
        amount=round(value, 2) if aggregation != "count" else None,
        count=int(value) if aggregation == "count" else len(rows),
        category=category, transaction_type=ttype, range=range_key,
    )
