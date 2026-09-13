"""Ranks the local LLM models configured in app/llm/config.py against a
small hand-labeled test set, per task (categorize, autocomplete) - so
swapping which model handles a task (see MODEL_FILES/TASK_MODEL) can be
backed by a real accuracy/latency comparison instead of a handful of manual
spot-checks.

Not part of the pytest suite: it needs the real multi-gigabyte .litertlm
files on disk and takes real wall-clock time (loading and running several
models back to back), so it's a manually-run tool, same as
scripts/seed_from_existing_xlsx.py - never touches a real user's database.

Usage (from budget_tracker/backend, with .venv active):
    python -m scripts.bench_llm
    python -m scripts.bench_llm --models qwen3_0_6b,deepseek_r1
    python -m scripts.bench_llm --tasks categorize
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def _summary(model_key: str, correct: int, total: int, errors: int, latencies: list[float]) -> dict:
    return {
        "model": model_key,
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
    header = f"{'#':<3}{'Model':<18}{'Score':<16}{'Errors':<8}{'Avg latency':<14}{'Total time'}"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(ranked, 1):
        name = MODEL_DISPLAY_NAMES.get(r["model"], r["model"])
        score = f"{r['correct']}/{r['total']} ({r['accuracy'] * 100:.0f}%)"
        print(f"{i:<3}{name:<18}{score:<16}{r['errors']:<8}{r['avg_latency']:.2f}s".ljust(60) + f"{r['total_time']:.1f}s")


TASKS = {"categorize": bench_categorize, "autocomplete": bench_autocomplete}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", help="Comma-separated model keys to test (default: all in MODEL_FILES)")
    parser.add_argument("--tasks", help="Comma-separated tasks to run: categorize,autocomplete (default: both)")
    args = parser.parse_args()

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

    print(f"Benchmarking {model_keys} on {task_names}...")
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
