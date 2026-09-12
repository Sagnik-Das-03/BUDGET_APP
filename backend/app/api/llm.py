import json
import re
import time
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
from app.repositories.chat import ChatRepository
from app.repositories.transactions import TransactionRepository
from app.schemas import (
    AskIn, AskOut, AskRowOut, AutocompleteIn, AutocompleteOut, CategorizeIn, CategorizeOut,
    ChatFeedbackIn, ChatMessageOut, ChatThreadOut, CompareRecapIn, CompareRecapOut, InsightOut,
    QuickAddIn, QuickAddOut, SuggestViewNameIn, SuggestViewNameOut,
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
    "last_3_months": "the last 3 months", "this_year": "this year", "all_time": "all time",
}


def _answer_is_faithful(text: str, aggregation: str, value: float, breakdown: list[dict]) -> bool:
    """Whether a phrased answer actually contains the real computed figure(s)
    verbatim, rather than a paraphrase that quietly changed the number - the
    only defense against a small model altering a value while "just" phrasing
    it (a real observed failure: 692,075 rendered back as 672,312)."""
    if aggregation == "breakdown":
        if not breakdown:
            return True
        top = breakdown[0]
        return top["category"] in text and f"{top['total']:,.0f}" in text
    if aggregation == "count":
        return str(int(value)) in text
    return f"{value:,.0f}" in text


def _resolve_named_range(range_key: str, date_from: Optional[date_type] = None,
                          date_to: Optional[date_type] = None) -> tuple[Optional[date_type], Optional[date_type]]:
    """this_week/this_month/this_year/all_time/custom go through the dashboard's
    own resolver (single source of truth for what those mean); last_month is
    an addition dashboard doesn't need but chat/recap questions often do."""
    if range_key == "last_month":
        return calc._range_previous_month(calc.range_this_month()[0])
    if range_key == "last_3_months":
        today = date_type.today()
        return today - timedelta(days=90), today
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


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_SUGGEST_VIEW_NAME_SYSTEM = (
    "You write a short, natural title (2-4 words, Title Case, no punctuation) for a saved "
    "transaction filter in a personal budget tracker app. Describe what the filter shows in "
    "plain language - do not just restate the field labels verbatim.\n\n"
    "Examples:\n"
    "Filter: Categories: Food-Order\n"
    "Title: Food Orders\n\n"
    "Filter: Excludes categories: Food-Order, Quick-Commerce; Type: Expense\n"
    "Title: Other Expenses\n\n"
    "Filter: Description contains: Zomato\n"
    "Title: Zomato Purchases\n\n"
    "Filter: Year: 2026; Month: September\n"
    "Title: September 2026\n\n"
    "Filter: Type: Income\n"
    "Title: All Income"
)


def _describe_view_filters(payload: SuggestViewNameIn) -> list[str]:
    parts = []
    if payload.category:
        label = "Excludes categories" if payload.category_exclude else "Categories"
        parts.append(f"{label}: {', '.join(payload.category)}")
    if payload.account:
        label = "Excludes accounts" if payload.account_exclude else "Accounts"
        parts.append(f"{label}: {', '.join(payload.account)}")
    if payload.type:
        parts.append(f"Type: {payload.type}")
    if payload.search:
        parts.append(f"Description contains: {payload.search}")
    if payload.year:
        parts.append(f"Year: {payload.year}")
    if payload.month:
        try:
            parts.append(f"Month: {_MONTH_NAMES[int(payload.month) - 1]}")
        except (ValueError, IndexError):
            parts.append(f"Month: {payload.month}")
    return parts


@router.post("/suggest_view_name", response_model=SuggestViewNameOut)
def suggest_view_name(payload: SuggestViewNameIn):
    if not llm_router.available:
        return SuggestViewNameOut(name="")

    parts = _describe_view_filters(payload)
    if not parts:
        return SuggestViewNameOut(name="")

    prompt = f"Filter: {'; '.join(parts)}\nTitle:"
    try:
        name = llm_router.complete(
            "suggest_view_name", prompt, system_message=_SUGGEST_VIEW_NAME_SYSTEM, max_output_tokens=16,
        )
    except Exception:
        return SuggestViewNameOut(name="")

    # The model sometimes rambles past the title (an explanation, a second
    # example) instead of stopping - keep only the first line, and drop a
    # "Title:" prefix it occasionally echoes back from the prompt.
    name = name.strip().split("\n")[0]
    name = re.sub(r"^title:\s*", "", name, flags=re.IGNORECASE).strip().strip("\"'.,").strip()
    words = name.split()
    if len(words) > 6:
        name = " ".join(words[:6])
    return SuggestViewNameOut(name=name[:60])


_QUICK_ADD_AMOUNT = re.compile(r"(?:rs\.?|inr|₹)?\s?\d[\d,]*(?:\.\d+)?", re.IGNORECASE)
_QUICK_ADD_DATE_WORDS = re.compile(
    r"\b(today|yesterday|tomorrow|day before yesterday|on\s+the\s+\d{1,2}(?:st|nd|rd|th)?|"
    r"the\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:st|nd|rd|th)?)\b", re.IGNORECASE,
)
_QUICK_ADD_FILLER_WORDS = re.compile(r"\b(spent|paid|got|received|for|on|of|a|an)\b", re.IGNORECASE)


def _extract_quick_add_description(raw_text: str) -> str:
    """Derives the description from the user's own words via plain string
    manipulation rather than asking the model to echo it back - constrained
    JSON decoding proved reliable for the enum fields below, but testing
    showed it hallucinating this one free-text field outright (e.g.
    "Zomato 250 today" came back with description "Anda") even with the
    schema and prompt both saying to copy it verbatim."""
    # Date words first: an ordinal like "2nd" would otherwise have its leading
    # digit eaten by the amount pattern, leaving a stray "nd" behind.
    cleaned = _QUICK_ADD_DATE_WORDS.sub(" ", raw_text)
    cleaned = _QUICK_ADD_AMOUNT.sub(" ", cleaned)
    cleaned = _QUICK_ADD_FILLER_WORDS.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned or raw_text.strip()


def _extract_quick_add_amount(raw_text: str) -> Optional[float]:
    """Derives the amount from the user's own text via the same regex used to
    STRIP it when building the description, rather than trusting the model's
    numeric field - testing showed the model occasionally emitting a
    nonsensical near-zero figure (e.g. 0.000000000000000001) instead of the
    actual amount, even under schema-constrained decoding ("180" in "coffee
    at starbucks 180 today" became that, not 180). Date words are stripped
    first so a phrase like "2 days ago" doesn't have its "2" mistaken for
    the amount."""
    cleaned = _QUICK_ADD_DATE_WORDS.sub(" ", raw_text)
    match = _QUICK_ADD_AMOUNT.search(cleaned)
    if not match:
        return None
    try:
        value = float(re.sub(r"[^\d.]", "", match.group()))
    except ValueError:
        return None
    return value if value > 0 else None


@router.post("/quick_add", response_model=QuickAddOut)
def quick_add(payload: QuickAddIn, session: Session = Depends(get_session)):
    """Parses a one-line description like 'Zomato 250 today' or 'got salary
    87000 yesterday' into a draft transaction for the user to review before
    saving - never creates anything itself. days_ago (a small integer) is
    used instead of asking the model for an absolute date, since that's a
    much safer thing for it to get right than date arithmetic; description
    and amount are both derived in Python from the user's own text (see
    _extract_quick_add_description/_extract_quick_add_amount), the model's
    own values there are only a fallback - only category/transaction_type/
    days_ago are trusted from the model's structured output."""
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
            # 64, not 40 - 40 was occasionally too tight to finish the closing
            # brace for a longer category name (e.g. "Quick-Commerce"),
            # producing a truncated, unparseable JSON string.
            "quick_add", prompt, system_message=system_message, schema=schema, max_output_tokens=64,
        )
    except Exception as e:
        raise HTTPException(503, f"Couldn't understand that ({e})") from e

    # Prefer the amount found directly in the user's own text over the
    # model's numeric field - see _extract_quick_add_amount's docstring.
    amount = _extract_quick_add_amount(text)
    if amount is None:
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

    txn_date = date_type.today() - timedelta(days=days_ago)
    # Matches this user's own existing naming convention (e.g. "Zomato (28/08/26)").
    description = f"{_extract_quick_add_description(text)} ({txn_date.strftime('%d/%m/%y')})"

    return QuickAddOut(
        date=txn_date, description=description,
        amount=round(amount, 2), transaction_type=ttype, category=category, account="Primary",
    )


@router.get("/insight", response_model=InsightOut)
def insight(range: str = "this_month", date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
            label: Optional[str] = None, session: Session = Depends(get_session)):
    """A single detailed narrative for whichever range/period the caller is
    currently looking at, replacing what used to be two separate features (a
    short recap + a one-line anomaly summary) with one longer explanation
    that covers both: the overall income/spending/savings picture AND a
    call-out of anything unusual detected in the period (see
    calc.detect_anomalies), including a guess at whether an unusual
    transaction is a real spending spike or just a miscategorized one-off.
    range is one of _RANGE_LABELS' keys, or "custom" with date_from/date_to
    (e.g. a drilled-into month on the Dashboard). `label` is an optional
    human-readable description of a custom range for the prompt (falls back
    to the raw dates)."""
    if not llm_router.available:
        raise HTTPException(503, "AI features are not available")

    d_from, d_to = _resolve_named_range(range, date_from, date_to)
    totals = calc.totals(session, d_from, d_to)
    top_categories = calc.by_category(session, d_from, d_to, transaction_type="Expense")[:8]
    anomalies = calc.detect_anomalies(session, d_from, d_to)

    if not top_categories and not totals["income"]:
        return InsightOut(insight="Not enough data yet to generate an explanation for this period.", range=range)

    period_desc = label or _RANGE_LABELS.get(range) or (f"{d_from} to {d_to}" if d_from and d_to else "all time")
    category_lines = "\n".join(f"- {c['category']}: Rs {c['total']:,.0f}" for c in top_categories) or "- (none)"
    anomaly_lines = "\n".join(
        f"- {a['description']}: Rs {a['amount']:,.0f} ({a['multiple']:.1f}x the usual Rs {a['category_avg']:,.0f} for {a['category']})"
        for a in anomalies
    ) or "- (nothing unusual flagged)"
    prompt = (
        f"Period: {period_desc}\n"
        f"Income: Rs {totals['income']:,.0f}\n"
        f"Expenses: Rs {totals['expenses']:,.0f}\n"
        f"Net savings: Rs {totals['net']:,.0f}\n"
        f"Savings rate: {totals['savings_rate'] * 100:.1f}%\n"
        f"Top expense categories:\n{category_lines}\n\n"
        f"Unusual transactions flagged this period:\n{anomaly_lines}\n\n"
        "Write a longer, detailed explanation (7-10 sentences, flowing prose - not a bulleted list) of "
        "this period's finances for the user. Cover the overall income/spending/savings picture, which "
        "categories dominated and why that might be, and the savings rate. Then address the unusual "
        "transactions listed above one by one if there are any - for each, say whether it looks like a "
        "real spending spike or just a miscategorized one-off (e.g. \"Table and Chair Bought\" filed "
        "under Utilities is furniture, not a utility bill), or whether an extreme multiple (over 20x) "
        "just means that category's history is too thin to be a fair baseline. If nothing unusual was "
        "flagged, say so briefly instead of inventing something. Be specific with the numbers given "
        "above - do not invent new ones."
    )
    try:
        insight_text = llm_router.complete(
            "summarize", prompt,
            system_message=(
                "You are a friendly personal-finance assistant writing a detailed, narrative explanation "
                "of a spending period - thorough rather than terse."
            ),
            max_output_tokens=450,
        )
    except Exception as e:
        raise HTTPException(503, f"Failed to generate explanation: {e}") from e

    return InsightOut(
        insight=insight_text or "Not enough data yet to generate an explanation for this period.", range=range,
    )


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


@router.get("/model_status/{task}")
def model_status(task: str):
    if task not in TASK_MODEL:
        raise HTTPException(404, f"Unknown task: {task}")
    return {"task": task, "available": llm_router.available, "loaded": llm_router.is_loaded(task)}


@router.post("/warmup/{task}")
def warmup(task: str):
    if task not in TASK_MODEL:
        raise HTTPException(404, f"Unknown task: {task}")
    if not llm_router.available:
        raise HTTPException(503, llm_router.unavailable_reason or "AI features aren't available right now.")
    try:
        llm_router.warm_up_task(task)
    except Exception as e:
        raise HTTPException(503, f"Failed to load model: {e}") from e
    return {"task": task, "loaded": True}


@router.get("/chat/threads", response_model=list[ChatThreadOut])
def list_chat_threads(session: Session = Depends(get_session)):
    return ChatRepository(session).list_threads()


@router.post("/chat/threads", response_model=ChatThreadOut)
def create_chat_thread(session: Session = Depends(get_session)):
    thread = ChatRepository(session).create_thread()
    session.commit()
    return thread


@router.get("/chat/threads/{thread_id}/messages", response_model=list[ChatMessageOut])
def list_chat_messages(thread_id: int, session: Session = Depends(get_session)):
    return ChatRepository(session).list_messages(thread_id)


@router.delete("/chat/threads/{thread_id}")
def delete_chat_thread(thread_id: int, session: Session = Depends(get_session)):
    deleted = ChatRepository(session).delete_thread(thread_id)
    session.commit()
    if not deleted:
        raise HTTPException(404, "Thread not found")
    return {"deleted": True}


@router.post("/chat/messages/{message_id}/feedback")
def chat_feedback(message_id: int, payload: ChatFeedbackIn, session: Session = Depends(get_session)):
    chat = ChatRepository(session)
    message = chat.set_feedback(message_id, payload.helpful, payload.note)
    if not message:
        raise HTTPException(404, "Message not found")
    # A thumbs-down becomes a standing correction the NEXT extraction call
    # sees (see the "Known past mistakes" block in ask()) - the realistic
    # substitute for fine-tuning a small local model on feedback.
    if not payload.helpful:
        chat.add_correction(message.question, message.query_json, payload.note)
    session.commit()
    return {"recorded": True}


@router.post("/ask", response_model=AskOut)
def ask(payload: AskIn, session: Session = Depends(get_session)):
    started_at = time.monotonic()
    question = payload.question.strip()
    chat = ChatRepository(session)
    thread = chat.get_thread(payload.thread_id) if payload.thread_id else None
    if not thread:
        thread = chat.create_thread()

    if not llm_router.available:
        answer = "AI features aren't available right now."
        duration_sec = time.monotonic() - started_at
        message = chat.add_message(thread.id, question, answer, duration_sec)
        session.commit()
        return AskOut(answer=answer, range="this_month", thread_id=thread.id, duration_sec=duration_sec, message_id=message.id)

    # Last few exchanges in this thread, so a follow-up like "what about last
    # month?" or "and just food?" can be resolved against what was already
    # asked instead of being extracted as a standalone, context-free query.
    # Capped at 5 to keep the prompt short - old exchanges matter far less
    # than the immediately preceding one.
    prior_messages = chat.list_messages(thread.id)[-5:]
    history_context = "\n".join(f'Q: "{m.question}"\nA: "{m.answer}"' for m in prior_messages)

    category_repo = CategoryRepository(session)
    category_objs = category_repo.list()
    categories = [c.name for c in category_objs]
    essential_names = [c.name for c in category_objs if c.is_essential]
    discretionary_names = [c.name for c in category_objs if not c.is_essential]

    # A growing memory of confirmed mistakes (from a thumbs-down on a past
    # answer, see /chat/messages/{id}/feedback) - not model fine-tuning (not
    # practical for a small local quantized model), but the realistic form
    # "learning from feedback" can take here: recent corrections are shown to
    # the extractor as concrete examples of what NOT to do again.
    corrections = chat.recent_corrections(limit=5)
    corrections_context = "\n".join(
        f'- "{c.question}" - {c.note}' for c in corrections if c.note
    )

    schema = {
        "type": "object",
        "properties": {
            "categories": {"type": "array", "items": {"type": "string", "enum": categories}},
            "exclude_categories": {"type": "array", "items": {"type": "string", "enum": categories}},
            "transaction_type": {"type": "string", "enum": ["Income", "Expense", "ANY"]},
            "range_type": {
                "type": "string",
                "enum": ["this_week", "this_month", "last_month", "last_n_days", "last_n_months", "this_year", "all_time"],
            },
            "range_n": {"type": "integer", "minimum": 1, "maximum": 365},
            "aggregation": {"type": "string", "enum": ["sum", "count", "avg", "breakdown"]},
            "keyword": {"type": "string"},
        },
        "required": [
            "categories", "exclude_categories", "transaction_type", "range_type", "range_n", "aggregation", "keyword",
        ],
        "additionalProperties": False,
    }
    prompt = (
        (f"Conversation so far in this chat:\n{history_context}\n\n" if history_context else "")
        + (f"Known past mistakes on similar questions - do not repeat these:\n{corrections_context}\n\n"
           if corrections_context else "")
        + f"Today's date: {date_type.today().isoformat()}\n"
        + f'New user question: "{question}"\n'
        + "Extract this new question as a structured query, resolving it against the conversation above if it "
        "references something earlier (e.g. a follow-up like \"what about last month?\" or \"and just food?\")."
    )
    # The enum/array constraints only guarantee STRUCTURALLY valid values come
    # back (real category names, integers in range) - not semantically correct
    # ones, so the model still needs the actual category names spelled out in
    # readable text to match "food" to "Food-Order", etc. Dates are computed
    # here in Python from range_type/range_n rather than trusting a small
    # model's own date arithmetic, which is far more error-prone.
    system_message = (
        "You convert a personal-finance question into a structured query, using the conversation history (if "
        "given) to resolve follow-up questions that don't repeat context on their own - e.g. if the previous "
        "question was about \"Food-Order last month\" and the new one is just \"what about this month?\", carry "
        "the category over and only change what the new question actually changed.\n"
        f"Available categories: {', '.join(categories)}.\n"
        f"Essential (fixed obligation) categories: {', '.join(essential_names) or '(none)'}.\n"
        f"Discretionary (flexible spending) categories: {', '.join(discretionary_names) or '(none)'}.\n"
        "categories: specific categories the question is about - leave empty for all categories. If the "
        'question asks about "essential"/"fixed" or "discretionary"/"flexible" spending, put ALL of the '
        "matching list above into categories.\n"
        'exclude_categories: categories to leave out, e.g. "...aside from rent" -> exclude_categories=["Rent"]. '
        "Only set one of categories/exclude_categories, never both.\n"
        "keyword: a specific merchant, item, or note mentioned in the question that ISN'T one of the categories "
        'above - e.g. "Zomato", "Uber", "electricity bill" - searched directly against the actual transaction '
        'descriptions instead of guessing a category for it. Leave as "" when the question is about a whole '
        "category or is general, not one specific thing.\n"
        'transaction_type: "Income", "Expense", or "ANY" if unspecified.\n'
        'range_type: "this_week", "this_month", "last_month" (the previous calendar month), "last_n_days" or '
        '"last_n_months" (for "last/past N days|weeks|months" phrasing - use range_n for the number, and use '
        'months for a "weeks" phrasing too), "this_year", or "all_time" (no time limit; use this if no time '
        "period is mentioned).\n"
        "range_n: the N for last_n_days/last_n_months (ignored otherwise - just set it to 1).\n"
        'aggregation: "count" for how-many questions, "avg" for average, "breakdown" when the question asks '
        'WHICH category or categories rather than for one total, otherwise "sum".'
    )
    try:
        parsed = llm_router.complete_json(
            "query_parse", prompt, system_message=system_message, schema=schema, max_output_tokens=120,
        )
    except Exception as e:
        answer = f"Couldn't understand that question ({e})."
        duration_sec = time.monotonic() - started_at
        message = chat.add_message(thread.id, question, answer, duration_sec)
        session.commit()
        return AskOut(answer=answer, range="this_month", thread_id=thread.id, duration_sec=duration_sec, message_id=message.id)

    categories_in = [c for c in (parsed.get("categories") or []) if c in categories]
    exclude_in = [c for c in (parsed.get("exclude_categories") or []) if c in categories]
    ttype = parsed.get("transaction_type")
    ttype = ttype if ttype in ("Income", "Expense") else None
    valid_range_types = {"this_week", "this_month", "last_month", "last_n_days", "last_n_months", "this_year", "all_time"}
    range_type = parsed.get("range_type") if parsed.get("range_type") in valid_range_types else "this_month"
    range_n = parsed.get("range_n")
    range_n = range_n if isinstance(range_n, int) and 1 <= range_n <= 365 else 1
    aggregation = parsed.get("aggregation") if parsed.get("aggregation") in ("sum", "count", "avg", "breakdown") else "sum"
    keyword = (parsed.get("keyword") or "").strip()[:80]

    today = date_type.today()
    if range_type == "last_n_days":
        date_from, date_to = today - timedelta(days=range_n), today
        period_label = f"the last {range_n} day{'s' if range_n != 1 else ''}"
        range_key = "last_n_days"
    elif range_type == "last_n_months":
        date_from, date_to = today - timedelta(days=30 * range_n), today
        period_label = f"the last {range_n} month{'s' if range_n != 1 else ''}"
        range_key = "last_n_months"
    else:
        date_from, date_to = _resolve_named_range(range_type)
        period_label = _RANGE_LABELS.get(range_type, range_type)
        range_key = range_type

    category_ids = None
    category_exclude = False
    if categories_in:
        category_ids = [c.id for c in (category_repo.get_by_name(n) for n in categories_in) if c] or None
    elif exclude_in:
        category_ids = [c.id for c in (category_repo.get_by_name(n) for n in exclude_in) if c] or None
        category_exclude = True

    # What was actually extracted for this question - stored on the message so
    # a later thumbs-down has something concrete to correct against.
    query_json = json.dumps({
        "categories": categories_in, "exclude_categories": exclude_in, "transaction_type": ttype,
        "range_type": range_type, "range_n": range_n, "aggregation": aggregation, "keyword": keyword,
    })

    scope_parts = []
    if categories_in:
        scope_parts.append(f"on {', '.join(categories_in)}")
    elif exclude_in:
        scope_parts.append(f"outside {', '.join(exclude_in)}")
    if keyword:
        scope_parts.append(f'matching "{keyword}"')
    scope = " ".join(scope_parts) or "overall"
    type_label = f" ({ttype.lower()})" if ttype else ""

    # Every aggregation mode - including breakdown - is computed from this same
    # set of actually-matching rows, rather than a separately-queried, more
    # rigid "by category" helper: a keyword search or an exclude-list narrows
    # the real data first, and the answer is whatever's actually found in it.
    rows = TransactionRepository(session).filter(
        category_ids=category_ids, category_exclude=category_exclude,
        transaction_type=ttype, date_from=date_from, date_to=date_to,
        search=keyword or None,
    )

    breakdown: list[dict] = []
    if aggregation == "breakdown":
        totals_by_category: dict[str, float] = {}
        for r in rows:
            name = r.category.name
            totals_by_category[name] = totals_by_category.get(name, 0.0) + r.amount
        breakdown = sorted(
            ({"category": name, "total": round(total, 2)} for name, total in totals_by_category.items()),
            key=lambda b: -b["total"],
        )[:8]

        value = breakdown[0]["total"] if breakdown else 0.0
        if not breakdown:
            fallback_answer = f"No transactions found {scope}{type_label} {period_label}."
        else:
            top = breakdown[0]
            fallback_answer = (
                f"Your top category {scope} {period_label} was {top['category']} at Rs {top['total']:,.0f}."
            )
    else:
        if aggregation == "count":
            value = float(len(rows))
        elif aggregation == "avg":
            value = (sum(r.amount for r in rows) / len(rows)) if rows else 0.0
        else:
            value = sum(r.amount for r in rows)

        if aggregation == "count":
            fallback_answer = f"You had {int(value)} transaction{'s' if value != 1 else ''} {scope}{type_label} {period_label}."
        elif aggregation == "avg":
            fallback_answer = f"Your average transaction {scope}{type_label} {period_label} was Rs {value:,.0f}."
        elif ttype == "Income":
            fallback_answer = f"You received Rs {value:,.0f} {scope} {period_label}."
        else:
            fallback_answer = f"You spent Rs {value:,.0f} {scope}{type_label} {period_label}."

    # A second, short model call to phrase the final answer naturally instead
    # of returning the rigid template above verbatim - it still does none of
    # the arithmetic (that already happened in Python above), it only gets to
    # choose how to say it. Grounded with the period's real totals (and, for a
    # breakdown query, the actual computed breakdown) as context it MAY
    # reference, but the computed number(s) above are what must appear - the
    # fallback template is used verbatim if this call fails.
    answer = fallback_answer
    if llm_router.available:
        # Only a "sum" question is actually about the period's money totals -
        # count/avg/breakdown answers have nothing to do with income/expense/
        # net or a category list, and including that context anyway (as this
        # used to, unconditionally) gave the small model unrelated numbers to
        # blend together - e.g. "how many transactions this year?" (aggregation
        # = count, real answer 245) came back as a fabricated 215 once the
        # prompt also threw in income/expense/net and a category breakdown it
        # had no reason to reference. Keep each mode's prompt to only the
        # numbers that question type actually needs.
        context_line = ""
        if aggregation == "breakdown":
            lines = "\n".join(f"- {r['category']}: Rs {r['total']:,.0f}" for r in breakdown) or "- (none)"
            computed_line = f"Computed breakdown ({scope}{type_label}, {period_label}):\n{lines}\n"
        elif aggregation == "count":
            computed_line = (
                f"Computed answer: {int(value)} transaction{'s' if int(value) != 1 else ''} "
                f"{scope}{type_label}, {period_label}.\n"
            )
        elif aggregation == "avg":
            computed_line = (
                f"Computed answer: average = Rs {value:,.0f} per transaction, {scope}{type_label}, {period_label} "
                f"(from {len(rows)} transaction{'s' if len(rows) != 1 else ''}).\n"
            )
        else:
            computed_line = (
                f"Computed answer: sum = Rs {value:,.0f}, {scope}{type_label}, {period_label} "
                f"(from {len(rows)} transaction{'s' if len(rows) != 1 else ''}).\n"
            )
            period_totals = calc.totals(session, date_from, date_to)
            context_line = (
                f"Period totals for context - Income: Rs {period_totals['income']:,.0f}, "
                f"Expenses: Rs {period_totals['expenses']:,.0f}, Net: Rs {period_totals['net']:,.0f}.\n"
            )
            # The extractor above resolves to only ONE aggregation, so a compound
            # question (e.g. "...and which category aside from rent") would have
            # no real data for its second half without this - the phrasing model
            # would otherwise fabricate a category/percentage to sound complete.
            if not categories_in:
                extra = calc.by_category(session, date_from, date_to, transaction_type="Expense")
                if exclude_in:
                    extra = [r for r in extra if r["category"] not in exclude_in]
                extra = extra[:6]
                if extra:
                    extra_lines = "\n".join(f"- {r['category']}: Rs {r['total']:,.0f}" for r in extra)
                    context_line += f"\nTop expense categories this period (only ones you may name):\n{extra_lines}\n"
        # No conversation history here, on purpose: an earlier version included
        # the previous Q&A and told the model to "phrase it so the reply flows
        # naturally (e.g. 'and last month it was...')" - a real question asked
        # only about this year came back with a fabricated, unrequested "last
        # month" comparison, because the model took the example literally. The
        # previous exchange also isn't guaranteed to have been correct itself
        # (this whole feature exists because it sometimes isn't), so echoing it
        # back risks compounding an old wrong number into a new answer. History
        # is only used for the EARLIER extraction step (deciding what the new
        # question is asking, where it's grammar-constrained and can't corrupt
        # a figure) - phrasing gets nothing to paraphrase beyond the number(s)
        # actually computed for this question, and nothing else to imitate.
        prompt = (
            f'User question: "{question}"\n'
            f"{computed_line}"
            f"{context_line}\n"
            "Answer the user's question directly in ONE-TWO natural, friendly sentences, using the computed "
            "answer/breakdown above as the headline and nothing else - do not add income/expense/net totals, a "
            "category breakdown, or a comparison to any other period unless they were actually given to you "
            "above. You may reference extra context given above only if the arithmetic is simple and exact - if "
            "the question asks about something not covered by the numbers given, say you don't have that "
            "instead of guessing. Never invent a number, category, or percentage that isn't derivable from the "
            "ones given."
        )
        try:
            llm_answer = llm_router.complete(
                "summarize", prompt,
                system_message="You are a precise personal-finance assistant. Never invent figures - only use the ones given.",
                max_output_tokens=130,
            ).strip()
            # The model has, in practice, altered the actual computed figure
            # while phrasing it (692,075 rendered back as 672,312) - so the
            # phrased answer is only trusted if it demonstrably contains the
            # real number(s) verbatim; otherwise the exact deterministic
            # fallback_answer (already set above) is used instead.
            if llm_answer and _answer_is_faithful(llm_answer, aggregation, value, breakdown):
                answer = llm_answer
        except Exception:
            pass  # fallback_answer already set

    duration_sec = time.monotonic() - started_at
    message = chat.add_message(thread.id, question, answer, duration_sec, query_json)
    session.commit()

    # The actual matching rows behind the answer (capped, most recent first -
    # `rows` is already ordered that way) so you can see exactly what was
    # found rather than only trusting the phrased sentence.
    row_outs = [
        AskRowOut(
            date=r.date, description=r.description, amount=r.amount,
            transaction_type=r.transaction_type.value if hasattr(r.transaction_type, "value") else r.transaction_type,
            category=r.category.name,
        )
        for r in rows[:10]
    ]

    if aggregation == "breakdown":
        return AskOut(
            answer=answer,
            amount=round(value, 2) if breakdown else None,
            count=len(breakdown),
            category=breakdown[0]["category"] if breakdown else None,
            transaction_type=ttype, range=range_key,
            thread_id=thread.id, duration_sec=duration_sec,
            rows=row_outs, message_id=message.id,
        )

    return AskOut(
        answer=answer,
        amount=round(value, 2) if aggregation != "count" else None,
        count=int(value) if aggregation == "count" else len(rows),
        category=categories_in[0] if len(categories_in) == 1 else None,
        transaction_type=ttype, range=range_key,
        thread_id=thread.id, duration_sec=duration_sec,
        rows=row_outs, message_id=message.id,
    )
