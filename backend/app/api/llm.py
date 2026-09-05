from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dashboard import calculations as calc
from app.db import get_session
from app.llm.router import llm_router
from app.repositories.categories import CategoryRepository
from app.repositories.transactions import TransactionRepository
from app.schemas import (
    AskIn, AskOut, AutocompleteIn, AutocompleteOut, CategorizeIn, CategorizeOut, MonthlyRecapOut,
)
from app.utils import period_key_for

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status")
def llm_status():
    return {"available": llm_router.available, "reason": llm_router.unavailable_reason}


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
        return AutocompleteOut(suggestion=prefix_matches[0])

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
    return AutocompleteOut(suggestion=suggestion)


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


@router.get("/monthly_recap", response_model=MonthlyRecapOut)
def monthly_recap(period_key: Optional[str] = None, session: Session = Depends(get_session)):
    if not llm_router.available:
        raise HTTPException(503, "AI features are not available")

    if period_key:
        d_from, d_to = calc.period_start(period_key), calc.period_end(period_key)
    else:
        d_from, d_to = calc.range_this_month()
        period_key = period_key_for(date_type.today())

    totals = calc.totals(session, d_from, d_to)
    top_categories = calc.by_category(session, d_from, d_to, transaction_type="Expense")[:8]

    if not top_categories and not totals["income"]:
        return MonthlyRecapOut(recap="Not enough data yet to generate a recap for this period.", period_key=period_key)

    category_lines = "\n".join(f"- {c['category']}: Rs {c['total']:,.0f}" for c in top_categories) or "- (none)"
    prompt = (
        f"Income: Rs {totals['income']:,.0f}\n"
        f"Expenses: Rs {totals['expenses']:,.0f}\n"
        f"Net savings: Rs {totals['net']:,.0f}\n"
        f"Savings rate: {totals['savings_rate'] * 100:.1f}%\n"
        f"Top expense categories:\n{category_lines}\n\n"
        "Write a short, friendly 3-4 sentence recap of this month's finances for the user. "
        "Mention anything notable (a dominant category, a good or concerning savings rate). "
        "Be specific with the numbers given above - do not invent new ones."
    )
    try:
        recap = llm_router.complete(
            "summarize", prompt,
            system_message="You are a friendly personal-finance assistant writing a short monthly recap.",
            max_output_tokens=220,
        )
    except Exception as e:
        raise HTTPException(503, f"Failed to generate recap: {e}") from e

    return MonthlyRecapOut(recap=recap or "Not enough data yet to generate a recap for this period.", period_key=period_key)


_RANGE_LABELS = {
    "this_week": "this week", "this_month": "this month", "last_month": "last month",
    "this_year": "this year", "all_time": "all time",
}


def _resolve_ask_range(range_key: str) -> tuple[Optional[date_type], Optional[date_type]]:
    if range_key == "last_month":
        return calc._range_previous_month(calc.range_this_month()[0])
    if range_key == "this_week":
        return calc.range_this_week()
    if range_key == "this_year":
        return calc.range_this_year()
    if range_key == "all_time":
        return None, None
    return calc.range_this_month()


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

    date_from, date_to = _resolve_ask_range(range_key)
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
