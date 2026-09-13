"""Ranks the local LLM models configured in app/llm/config.py against a
small hand-labeled test set, per task - every AI task the app has (see TASKS
below: categorize, autocomplete, suggest_view_name, quick_add, query_parse,
summarize) - so swapping which model handles a task (see MODEL_FILES/
TASK_MODEL) can be backed by a real accuracy/latency comparison instead of a
handful of manual spot-checks.

Not part of the pytest suite: it needs the real multi-gigabyte .litertlm
files on disk and takes real wall-clock time (loading and running several
models back to back), so it's a manually-run tool, same as
scripts/seed_from_existing_xlsx.py - never touches a real user's database.

Usage (from budget_tracker/backend, with .venv active):
    cd budget_tracker/backend
    .venv/Scripts/activate
    python -m scripts.bench_llm
    python -m scripts.bench_llm --models qwen3_0_6b,deepseek_r1
    python -m scripts.bench_llm --tasks categorize,query_parse
    python -m scripts.bench_llm --backend gpu
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.llm.config import MODEL_DISPLAY_NAMES, MODEL_FILES, TASK_MODEL  # noqa: E402
from app.llm.router import llm_router  # noqa: E402

# Mirrors app/repositories/categories.py's DEFAULT_CATEGORIES names - kept as
# a plain list here (rather than importing and hitting a real database) since
# this only needs the names, not the full seeded rows.
CATEGORIES = [
    "Income", "Subscriptions", "Quick-Commerce", "Shopping", "Food-Order",
    "SIP", "Savings", "Gift", "RENT", "Transport", "Utilities", "Travel", "Other",
]

# (description, expected category) - two per category, phrased like real
# transaction descriptions (see app/imports/csv_parser.py's CATEGORY_RULES
# for the same flavor of merchant names this app actually sees).
CATEGORIZE_CASES: list[tuple[str, str]] = [
    ("Salary credited for September", "Income"),
    ("Freelance payment received", "Income"),
    ("Netflix monthly subscription", "Subscriptions"),
    ("Spotify premium renewal", "Subscriptions"),
    ("Blinkit grocery delivery", "Quick-Commerce"),
    ("Zepto instant delivery order", "Quick-Commerce"),
    ("Amazon order electronics", "Shopping"),
    ("Myntra clothing purchase", "Shopping"),
    ("Zomato dinner order", "Food-Order"),
    ("Swiggy lunch delivery", "Food-Order"),
    ("Groww mutual fund SIP", "SIP"),
    ("Monthly SIP investment", "SIP"),
    ("UPI Lite wallet topup", "Savings"),
    ("Recurring deposit transfer to savings", "Savings"),
    ("Birthday gift for friend", "Gift"),
    ("Wedding gift contribution", "Gift"),
    ("Monthly house rent payment", "RENT"),
    ("Rent transfer to landlord", "RENT"),
    ("Uber ride to office", "Transport"),
    ("Ola cab booking", "Transport"),
    ("Electricity bill payment", "Utilities"),
    ("Broadband internet bill", "Utilities"),
    ("MakeMyTrip flight booking", "Travel"),
    ("IRCTC train ticket", "Travel"),
    ("ATM cash withdrawal", "Other"),
    ("Miscellaneous UPI payment to unknown merchant", "Other"),
]

# Partial descriptions a user might be mid-typing - autocomplete has no
# single "correct" continuation, so it's scored structurally instead (see
# _is_valid_autocomplete), the same shape of check the real endpoint itself
# applies in app/api/llm.py's autocomplete().
AUTOCOMPLETE_CASES: list[str] = [
    "Zomato ord", "Uber ride t", "Netflix sub", "Rent paym",
    "Salary cre", "Electricity bi", "Amazon ord", "Groww SIP inv",
]

# Pre-joined filter descriptions, matching what app/api/llm.py's
# _describe_view_filters() would produce - suggest_view_name has no single
# "correct" title either, scored structurally like autocomplete.
SUGGEST_VIEW_NAME_CASES: list[str] = [
    "Categories: Food-Order",
    "Excludes categories: Food-Order, Quick-Commerce; Type: Expense",
    "Description contains: Zomato",
    "Year: 2026; Month: September",
    "Type: Income",
]

# (user text, expected {transaction_type, category, days_ago}) - matches the
# 3 fields quick_add() actually trusts from the model (amount/description are
# derived in Python from the user's own text, not tested here).
QUICK_ADD_CASES: list[tuple[str, dict]] = [
    ("Zomato dinner 350 today", {"transaction_type": "Expense", "category": "Food-Order", "days_ago": 0}),
    ("got salary 87000 yesterday", {"transaction_type": "Income", "category": "Income", "days_ago": 1}),
    ("paid rent 15000 3 days ago", {"transaction_type": "Expense", "category": "RENT", "days_ago": 3}),
    ("Uber ride 220 today", {"transaction_type": "Expense", "category": "Transport", "days_ago": 0}),
    ("Netflix subscription 199 yesterday", {"transaction_type": "Expense", "category": "Subscriptions", "days_ago": 1}),
    ("electricity bill 1200 2 days ago", {"transaction_type": "Expense", "category": "Utilities", "days_ago": 2}),
]

# Mirrors app/repositories/categories.py's DEFAULT_CATEGORIES' is_essential
# flag - needed for query_parse's system message, which spells these two
# lists out explicitly (see app/api/llm.py's ask()).
ESSENTIAL_CATEGORIES = ["Income", "SIP", "Savings", "RENT", "Transport", "Utilities"]
DISCRETIONARY_CATEGORIES = ["Subscriptions", "Quick-Commerce", "Shopping", "Food-Order", "Gift", "Travel", "Other"]

# (question, expected structured query) - the "Ask your budget" extraction
# step. Picked to be unambiguous under app/api/llm.py's ask() system message
# (e.g. "ANY" only where the question genuinely doesn't specify a type), so
# there's really one right structured answer per question.
QUERY_PARSE_CASES: list[tuple[str, dict]] = [
    ("How much did I spend on food delivery last month?", {
        "categories": ["Food-Order"], "exclude_categories": [], "transaction_type": "Expense",
        "range_type": "last_month", "range_n": 1, "aggregation": "sum", "keyword": "",
    }),
    ("How many transactions do I have this year?", {
        "categories": [], "exclude_categories": [], "transaction_type": "ANY",
        "range_type": "this_year", "range_n": 1, "aggregation": "count", "keyword": "",
    }),
    ("What's my average spend on shopping this month?", {
        "categories": ["Shopping"], "exclude_categories": [], "transaction_type": "Expense",
        "range_type": "this_month", "range_n": 1, "aggregation": "avg", "keyword": "",
    }),
    ("Break down my expenses by category this year", {
        "categories": [], "exclude_categories": [], "transaction_type": "Expense",
        "range_type": "this_year", "range_n": 1, "aggregation": "breakdown", "keyword": "",
    }),
    ("How much have I spent on Zomato in the last 30 days?", {
        "categories": [], "exclude_categories": [], "transaction_type": "Expense",
        "range_type": "last_n_days", "range_n": 30, "aggregation": "sum", "keyword": "Zomato",
    }),
    ("What's my total income this year?", {
        "categories": [], "exclude_categories": [], "transaction_type": "Income",
        "range_type": "this_year", "range_n": 1, "aggregation": "sum", "keyword": "",
    }),
    ("How much did I spend this month excluding rent?", {
        "categories": [], "exclude_categories": ["RENT"], "transaction_type": "Expense",
        "range_type": "this_month", "range_n": 1, "aggregation": "sum", "keyword": "",
    }),
    ("How many transactions were categorized as Subscriptions this year?", {
        "categories": ["Subscriptions"], "exclude_categories": [], "transaction_type": "ANY",
        "range_type": "this_year", "range_n": 1, "aggregation": "count", "keyword": "",
    }),
]

# A fixed synthetic scenario for "summarize" (the Dashboard insight/recap/
# Ask-phrasing task) - free prose has no single correct answer, so it's
# scored structurally: reasonable length, and mentions at least most of the
# real figures given rather than inventing different ones (the prompt itself
# explicitly demands this - see app/api/llm.py's insight()).
_SUMMARIZE_FIGURES = [75000, 42000, 33000]
SUMMARIZE_PROMPT = (
    "Period: September 2026\n"
    "Income: Rs 75,000\n"
    "Expenses: Rs 42,000\n"
    "Net savings: Rs 33,000\n"
    "Savings rate: 44.0%\n"
    "Top expense categories:\n- Food-Order: Rs 12,000\n- Shopping: Rs 9,000\n\n"
    "Unusual transactions flagged this period:\n- (nothing unusual flagged)\n\n"
    "Write a longer, detailed explanation (7-10 sentences, flowing prose - not a bulleted list) of "
    "this period's finances for the user. Cover the overall income/spending/savings picture, which "
    "categories dominated and why that might be, and the savings rate. Be specific with the numbers "
    "given above - do not invent new ones."
)
SUMMARIZE_SYSTEM = (
    "The user's name is TestUser. You are a friendly personal-finance assistant writing a detailed, "
    "narrative explanation of a spending period - thorough rather than terse."
)


def _categorize_schema() -> dict:
    return {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": CATEGORIES}},
        "required": ["category"],
        "additionalProperties": False,
    }


def _is_valid_autocomplete(prefix: str, suggestion: str) -> bool:
    s = suggestion.strip().strip('"')
    return bool(s) and s.lower() != prefix.lower() and s.lower().startswith(prefix.lower()) and len(s) <= 80


def _is_valid_view_name(filter_desc: str, name: str) -> bool:
    n = name.strip().strip('"').strip()
    if not n or ":" in n or n.lower() == filter_desc.lower():
        return False
    word_count = len(n.split())
    return 1 <= word_count <= 6


def _quick_add_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "exclusiveMinimum": 0},
            "transaction_type": {"type": "string", "enum": ["Income", "Expense"]},
            "category": {"type": "string", "enum": CATEGORIES},
            "days_ago": {"type": "integer", "minimum": 0, "maximum": 365},
        },
        "required": ["amount", "transaction_type", "category", "days_ago"],
        "additionalProperties": False,
    }


def _quick_add_system() -> str:
    return (
        "You extract the structured details of a single financial transaction from a short user message.\n"
        f"Available categories: {', '.join(CATEGORIES)} - pick the closest match.\n"
        '"days_ago": how many days before today this happened - 0 for today/unspecified, 1 for yesterday, etc.\n'
        '"transaction_type": "Income" if money was received, otherwise "Expense".'
    )


def _query_parse_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "categories": {"type": "array", "items": {"type": "string", "enum": CATEGORIES}},
            "exclude_categories": {"type": "array", "items": {"type": "string", "enum": CATEGORIES}},
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


def _query_parse_system() -> str:
    return (
        "The user's name is TestUser.\n"
        "You convert a personal-finance question into a structured query, using the conversation history (if "
        "given) to resolve follow-up questions that don't repeat context on their own - e.g. if the previous "
        "question was about \"Food-Order last month\" and the new one is just \"what about this month?\", carry "
        "the category over and only change what the new question actually changed.\n"
        f"Available categories: {', '.join(CATEGORIES)}.\n"
        f"Essential (fixed obligation) categories: {', '.join(ESSENTIAL_CATEGORIES)}.\n"
        f"Discretionary (flexible spending) categories: {', '.join(DISCRETIONARY_CATEGORIES)}.\n"
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


def _query_parse_matches(expected: dict, actual: dict) -> bool:
    for key, value in expected.items():
        got = actual.get(key)
        if isinstance(value, list):
            if sorted(got or []) != sorted(value):
                return False
        elif got != value:
            return False
    return True


def _is_valid_summary(text: str) -> bool:
    if not text or len(text.split()) < 25:
        return False
    hits = sum(1 for n in _SUMMARIZE_FIGURES if f"{n:,}" in text or str(n) in text)
    return hits >= 2


def _unload(model_key: str) -> None:
    """Frees a model's engine right after its benchmarks finish, so running
    the full suite across every configured model doesn't need all of them
    resident in memory at once - only ever one at a time, same peak memory
    as normal single-task use."""
    engine = llm_router._engines.pop(model_key, None)
    if engine is not None:
        try:
            engine.close()
        except Exception:
            pass


def bench_categorize(model_key: str) -> dict:
    task = f"__bench_categorize_{model_key}"
    TASK_MODEL[task] = model_key
    correct = 0
    errors = 0
    latencies: list[float] = []
    for description, expected in CATEGORIZE_CASES:
        start = time.monotonic()
        guess = None
        try:
            result = llm_router.complete_json(
                task,
                f'Transaction description: "{description}"\nPick the single best matching category for it.',
                system_message="You categorize personal-finance transactions into one of a fixed set of categories.",
                schema=_categorize_schema(),
                max_output_tokens=40,
            )
            guess = result.get("category")
        except Exception:
            errors += 1
        latencies.append(time.monotonic() - start)
        if guess == expected:
            correct += 1
    return _summary(model_key, correct, len(CATEGORIZE_CASES), errors, latencies)


def bench_autocomplete(model_key: str) -> dict:
    task = f"__bench_autocomplete_{model_key}"
    TASK_MODEL[task] = model_key
    valid = 0
    errors = 0
    latencies: list[float] = []
    for prefix in AUTOCOMPLETE_CASES:
        start = time.monotonic()
        suggestion = ""
        try:
            suggestion = llm_router.complete(
                task, prefix,
                system_message="You autocomplete short transaction descriptions for a personal budget tracker app. Be concise.",
                max_output_tokens=24,
            )
        except Exception:
            errors += 1
        latencies.append(time.monotonic() - start)
        if _is_valid_autocomplete(prefix, suggestion):
            valid += 1
    return _summary(model_key, valid, len(AUTOCOMPLETE_CASES), errors, latencies)


def bench_suggest_view_name(model_key: str) -> dict:
    task = f"__bench_suggest_view_name_{model_key}"
    TASK_MODEL[task] = model_key
    valid = 0
    errors = 0
    latencies: list[float] = []
    for filter_desc in SUGGEST_VIEW_NAME_CASES:
        start = time.monotonic()
        name = ""
        try:
            name = llm_router.complete(
                task, f"Filter: {filter_desc}\nTitle:",
                system_message=(
                    "You write a short, natural title (2-4 words, Title Case, no punctuation) for a saved "
                    "transaction filter in a personal budget tracker app. Describe what the filter shows in "
                    "plain language - do not just restate the field labels verbatim.\n\n"
                    "Examples:\n"
                    "Filter: Categories: Food-Order\nTitle: Food Orders\n\n"
                    "Filter: Excludes categories: Food-Order, Quick-Commerce; Type: Expense\n"
                    "Title: Other Expenses\n\n"
                    "Filter: Description contains: Zomato\nTitle: Zomato Purchases\n\n"
                    "Filter: Year: 2026; Month: September\nTitle: September 2026\n\n"
                    "Filter: Type: Income\nTitle: All Income"
                ),
                max_output_tokens=16,
            )
        except Exception:
            errors += 1
        latencies.append(time.monotonic() - start)
        if _is_valid_view_name(filter_desc, name):
            valid += 1
    return _summary(model_key, valid, len(SUGGEST_VIEW_NAME_CASES), errors, latencies)


def bench_quick_add(model_key: str) -> dict:
    task = f"__bench_quick_add_{model_key}"
    TASK_MODEL[task] = model_key
    correct = 0
    errors = 0
    latencies: list[float] = []
    for text, expected in QUICK_ADD_CASES:
        start = time.monotonic()
        got = {}
        try:
            got = llm_router.complete_json(
                task,
                f'Today: 2026-09-13\nUser input: "{text}"\nExtract this as a transaction.',
                system_message=_quick_add_system(),
                schema=_quick_add_schema(),
                max_output_tokens=64,
            )
        except Exception:
            errors += 1
        latencies.append(time.monotonic() - start)
        if all(got.get(k) == v for k, v in expected.items()):
            correct += 1
    return _summary(model_key, correct, len(QUICK_ADD_CASES), errors, latencies)


def bench_query_parse(model_key: str) -> dict:
    task = f"__bench_query_parse_{model_key}"
    TASK_MODEL[task] = model_key
    correct = 0
    errors = 0
    latencies: list[float] = []
    for question, expected in QUERY_PARSE_CASES:
        start = time.monotonic()
        got = {}
        try:
            got = llm_router.complete_json(
                task,
                f'Today\'s date: 2026-09-13\nNew user question: "{question}"\n'
                "Extract this new question as a structured query.",
                system_message=_query_parse_system(),
                schema=_query_parse_schema(),
                max_output_tokens=120,
            )
        except Exception:
            errors += 1
        latencies.append(time.monotonic() - start)
        if _query_parse_matches(expected, got):
            correct += 1
    return _summary(model_key, correct, len(QUERY_PARSE_CASES), errors, latencies)


def bench_summarize(model_key: str) -> dict:
    task = f"__bench_summarize_{model_key}"
    TASK_MODEL[task] = model_key
    valid = 0
    errors = 0
    latencies: list[float] = []
    # Only one scenario (unlike the other tasks' several cases) - "summarize"
    # generates free prose, so there's no larger labeled set to run through;
    # this checks the one thing that actually matters structurally (see
    # _is_valid_summary), run once since the output is otherwise unscored.
    start = time.monotonic()
    text = ""
    try:
        text = llm_router.complete(
            task, SUMMARIZE_PROMPT, system_message=SUMMARIZE_SYSTEM, max_output_tokens=450,
        )
    except Exception:
        errors += 1
    latencies.append(time.monotonic() - start)
    if _is_valid_summary(text):
        valid += 1
    return _summary(model_key, valid, 1, errors, latencies)


def _summary(model_key: str, correct: int, total: int, errors: int, latencies: list[float]) -> dict:
    return {
        "model": model_key,
        # The backend that actually ended up serving these calls - may
        # differ from the requested --backend if GPU failed and the router
        # fell back to CPU mid-run (see app/llm/router.py); worth surfacing
        # since a "gpu" run that silently fell back isn't testing what it
        # looks like it's testing.
        "backend": llm_router.backend_for(model_key) or "?",
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else 0.0,
        "errors": errors,
        "avg_latency": sum(latencies) / len(latencies) if latencies else 0.0,
        "total_time": sum(latencies),
    }


def _print_ranking(title: str, results: list[dict]) -> None:
    ranked = sorted(results, key=lambda r: (-r["accuracy"], r["avg_latency"]))
    print(f"\n=== {title} (ranked best first) ===")
    header = f"{'#':<3}{'Model':<18}{'Backend':<9}{'Score':<16}{'Errors':<8}{'Avg latency':<14}{'Total time'}"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(ranked, 1):
        name = MODEL_DISPLAY_NAMES.get(r["model"], r["model"])
        score = f"{r['correct']}/{r['total']} ({r['accuracy'] * 100:.0f}%)"
        print(
            f"{i:<3}{name:<18}{r['backend']:<9}{score:<16}{r['errors']:<8}{r['avg_latency']:.2f}s".ljust(69)
            + f"{r['total_time']:.1f}s"
        )


TASKS = {
    "categorize": bench_categorize,
    "autocomplete": bench_autocomplete,
    "suggest_view_name": bench_suggest_view_name,
    "quick_add": bench_quick_add,
    "query_parse": bench_query_parse,
    "summarize": bench_summarize,
}


def _normalize_args(argv: list[str]) -> list[str]:
    """Tolerates "-- tasks categorize" (a stray space after "--") as well as
    the correct "--tasks categorize" - argparse treats a bare "--" as "end
    of options", turning everything after it into unrecognized positional
    arguments, which is a confusing error for what's really just a typo of
    a known flag name. Merges it back into "--tasks" before argparse ever
    sees it; anything else passes through untouched."""
    known = {"models", "tasks", "backend"}
    normalized = []
    i = 0
    while i < len(argv):
        if argv[i] == "--" and i + 1 < len(argv) and argv[i + 1] in known:
            normalized.append(f"--{argv[i + 1]}")
            i += 2
            continue
        normalized.append(argv[i])
        i += 1
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", help="Comma-separated model keys to test (default: all in MODEL_FILES)")
    parser.add_argument("--tasks", help="Comma-separated tasks to run: categorize,autocomplete (default: both)")
    parser.add_argument(
        "--backend", choices=["cpu", "gpu"],
        help="Override LLM_BACKEND for this run only (default: whatever's configured in .env, normally cpu). "
             "A failed GPU call falls back to CPU automatically (see app/llm/router.py) - the printed table's "
             "Backend column shows what actually served each model, so a silent fallback is visible.",
    )
    args = parser.parse_args(_normalize_args(sys.argv[1:]))

    model_keys = args.models.split(",") if args.models else list(MODEL_FILES)
    task_names = args.tasks.split(",") if args.tasks else list(TASKS)
    for key in model_keys:
        if key not in MODEL_FILES:
            parser.error(f"Unknown model {key!r} - choices are {list(MODEL_FILES)}")
    for name in task_names:
        if name not in TASKS:
            parser.error(f"Unknown task {name!r} - choices are {list(TASKS)}")

    if not llm_router.available:
        print(f"LLM features unavailable: {llm_router.unavailable_reason}")
        return

    if args.backend:
        settings.llm_backend = args.backend

    print(f"Benchmarking {model_keys} on {task_names} (backend={settings.llm_backend})...")
    results: dict[str, list[dict]] = {name: [] for name in task_names}
    for model_key in model_keys:
        print(f"\n--- {MODEL_DISPLAY_NAMES.get(model_key, model_key)} ---")
        for task_name in task_names:
            print(f"  {task_name}...", end=" ", flush=True)
            r = TASKS[task_name](model_key)
            results[task_name].append(r)
            print(f"{r['correct']}/{r['total']} ({r['accuracy'] * 100:.0f}%), "
                  f"{r['errors']} errors, {r['avg_latency']:.2f}s avg")
        _unload(model_key)

    for task_name in task_names:
        _print_ranking(task_name, results[task_name])

    llm_router.shutdown()


if __name__ == "__main__":
    main()
