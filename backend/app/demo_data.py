import random
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import TransactionType
from app.repositories.accounts import AccountRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.categories import CategoryRepository
from app.repositories.savings_goal import SavingsGoalRepository
from app.repositories.transactions import TransactionRepository

# Fixed seed - demo data should look the same every time it's (re)generated,
# not shuffle randomly and make screenshots/bug reports non-reproducible.
_SEED = 20260101


def _month_starts(months_back: int, today: date) -> list[date]:
    """The 1st of each of the last `months_back` calendar months, oldest first,
    ending with the current month - so demo data always looks "current"
    relative to whenever it's generated rather than pinned to a fixed year."""
    starts = []
    y, m = today.year, today.month
    for _ in range(months_back):
        starts.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(starts))


def _random_day(month_start: date, rng: random.Random, before: date) -> date:
    last_day = monthrange(month_start.year, month_start.month)[1]
    day = rng.randint(1, last_day)
    d = date(month_start.year, month_start.month, day)
    return min(d, before)


def seed_demo_data(session: Session, months_back: int = 12, today: date = None) -> None:
    """Populates a fresh user's database with a year of realistic, varied
    transactions (plus a couple of budgets and a savings goal) so every
    dashboard chart - trends, category breakdown, essential/discretionary
    split, anomalies, budget vs. actual, savings streak - has something real
    to show immediately, without needing the person to enter data first."""
    today = today or date.today()
    rng = random.Random(_SEED)

    category_repo = CategoryRepository(session)
    category_repo.ensure_defaults()
    cats = {c.name: c for c in category_repo.list()}
    account = AccountRepository(session).ensure_default()
    txns = TransactionRepository(session)

    def add(d: date, desc: str, amount: float, ttype: TransactionType, category_name: str):
        if d > today:
            return
        txns.create(
            date=d, description=desc, amount=round(amount, 2), transaction_type=ttype,
            category=cats[category_name], account=account,
        )

    for i, month_start in enumerate(_month_starts(months_back, today)):
        month_end = date(month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1])
        cap = min(month_end, today)

        # Salary - steady with a small raise partway through, and a bonus once.
        salary = 85000 + (5000 if i >= months_back // 2 else 0)
        add(date(month_start.year, month_start.month, 1), "Monthly Salary", salary, TransactionType.income, "Income")
        if i == months_back - 3:
            add(date(month_start.year, month_start.month, 5), "Annual Bonus", 40000, TransactionType.income, "Income")

        # Fixed monthly obligations.
        add(date(month_start.year, month_start.month, 3), "Rent (03/{:02d})".format(month_start.month),
            22000, TransactionType.expense, "RENT")
        add(_random_day(month_start, rng, cap), "Electricity + Internet", rng.uniform(2200, 3400),
            TransactionType.expense, "Utilities")
        add(date(month_start.year, month_start.month, 5), "Index Fund SIP", 8000, TransactionType.expense, "SIP")
        add(date(month_start.year, month_start.month, 5), "Recurring Savings Transfer", rng.uniform(4000, 9000),
            TransactionType.expense, "Savings")
        for sub, price in (("Netflix", 649), ("Spotify", 149), ("Cloud Storage", 199)):
            add(date(month_start.year, month_start.month, 7), sub, price, TransactionType.expense, "Subscriptions")

        # Variable day-to-day spending - several transactions per category per month.
        for _ in range(rng.randint(4, 8)):
            add(_random_day(month_start, rng, cap), rng.choice(
                ["Zomato order", "Swiggy order", "Coffee", "Lunch with team"]),
                rng.uniform(180, 750), TransactionType.expense, "Food-Order")
        for _ in range(rng.randint(3, 6)):
            add(_random_day(month_start, rng, cap), rng.choice(
                ["Blinkit", "Zepto grocery run", "Instamart"]),
                rng.uniform(300, 1400), TransactionType.expense, "Quick-Commerce")
        for _ in range(rng.randint(2, 5)):
            add(_random_day(month_start, rng, cap), rng.choice(
                ["Amazon order", "Clothing", "Electronics accessory"]),
                rng.uniform(500, 4000), TransactionType.expense, "Shopping")
        for _ in range(rng.randint(3, 7)):
            add(_random_day(month_start, rng, cap), rng.choice(
                ["Cab ride", "Auto", "Metro card top-up", "Fuel"]),
                rng.uniform(100, 900), TransactionType.expense, "Transport")

        # Occasional categories, not every month.
        if rng.random() < 0.4:
            add(_random_day(month_start, rng, cap), "Flight/train booking", rng.uniform(3000, 15000),
                TransactionType.expense, "Travel")
        if rng.random() < 0.25:
            add(_random_day(month_start, rng, cap), "Gift for family", rng.uniform(1000, 5000),
                TransactionType.expense, "Gift")
        if rng.random() < 0.2:
            add(_random_day(month_start, rng, cap), "Misc expense", rng.uniform(200, 1200),
                TransactionType.expense, "Other")

    # One deliberate anomaly - a Shopping spike well above that category's
    # normal range - so anomaly detection has something real to flag.
    anomaly_month = _month_starts(months_back, today)[-2]
    add(date(anomaly_month.year, anomaly_month.month, 18), "New Laptop", 62000, TransactionType.expense, "Shopping")

    budgets = BudgetRepository(session)
    budgets.set_goal(cats["Food-Order"], 6000)
    budgets.set_goal(cats["Shopping"], 8000)
    budgets.set_goal(cats["Quick-Commerce"], 5000)

    SavingsGoalRepository(session).set_goal(15000)
