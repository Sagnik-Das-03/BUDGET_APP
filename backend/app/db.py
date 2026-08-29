from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _add_missing_columns() -> None:
    """Lightweight, dependency-free migration for a single-user SQLite app: for
    each mapped table that already exists, ADD COLUMN for any column the model
    defines that the live table doesn't have yet. New tables are handled by
    create_all() below; this only covers columns added to an existing table
    (e.g. Category.counts_as_expense) so the app never needs a full DB wipe
    just because a model gained a field."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                default_clause = ""
                if column.default is not None and column.default.is_scalar:
                    default_clause = f" DEFAULT {column.default.arg!r}" if isinstance(column.default.arg, str) \
                        else f" DEFAULT {int(column.default.arg) if isinstance(column.default.arg, bool) else column.default.arg}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_clause}'))


def init_db() -> None:
    from app import models  # noqa: F401 - ensures models are registered on Base

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
