"""One-off cleanup: is_essential was added to Category as a NEW column with a
SQL-level DEFAULT of True (see app/db._add_missing_columns), so every
category that existed before this column was introduced got blanket
True ("essential") regardless of DEFAULT_CATEGORIES' actual per-category
guess (Shopping/Food-Order/Travel/etc default to discretionary there).
This applies those intended starting values to existing categories once.

Deliberately NOT folded into CategoryRepository.ensure_defaults(), which by
design only sets is_essential at category-creation time - once a category
exists, a user's own Settings choice must never be silently overwritten on a
later restart. This script predates any such choice being possible (the
Settings toggle didn't exist until this column did), so it's safe to run
once as a correction, not an ongoing sync.

Safe to re-run, but pointless after the first run: it only ever writes the
DEFAULT_CATEGORIES value, so a second run is a no-op unless DEFAULT_CATEGORIES
itself changes. Skips any category whose is_essential a user may have
already toggled away from the default in the meantime? It can't tell the
difference - re-running after manually adjusting a category via Settings
WOULD stomp that choice back to the seeded default, so don't re-run this
once you've started using the Settings toggle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db, session_scope  # noqa: E402
from app.repositories.categories import DEFAULT_CATEGORIES, CategoryRepository  # noqa: E402


def run() -> dict:
    init_db()
    changed = []
    with session_scope() as session:
        cat_repo = CategoryRepository(session)
        for name, _color, _counts_as_expense, is_essential in DEFAULT_CATEGORIES:
            cat = cat_repo.get_by_name(name)
            if cat and cat.is_essential != is_essential:
                changed.append((name, cat.is_essential, is_essential))
                cat.is_essential = is_essential
    return {"changed_count": len(changed), "changed": changed}


if __name__ == "__main__":
    result = run()
    print(f"Updated is_essential on {result['changed_count']} categories:")
    for name, old, new in result["changed"]:
        print(f"  {name:<16} {old} -> {new}")
