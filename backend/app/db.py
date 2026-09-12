from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings
from app.user_registry import registry

DEFAULT_USERNAME = "Sagnik"


class Base(DeclarativeBase):
    pass


def _db_path_for(db_file: str) -> Path:
    path = (BASE_DIR / "data" / db_file).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _initial_db_path() -> Path:
    """Which SQLite file this process opens at startup: the active user from
    the registry, bootstrapping the registry from the classic single-user
    db_path setting on first run - the existing database becomes user #1
    (DEFAULT_USERNAME) exactly where it already is, untouched."""
    registry.ensure_bootstrapped(DEFAULT_USERNAME, Path(settings.db_path).name)
    active = registry.get_active()
    db_file = registry.get_db_file(active) if active else None
    return _db_path_for(db_file or Path(settings.db_path).name)


engine = create_engine(f"sqlite:///{_initial_db_path()}", connect_args={"check_same_thread": False})
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


def switch_active_db(db_file: str) -> None:
    """Rebinds THIS PROCESS's engine/session factory to a different user's
    SQLite file and ensures its schema exists. Every other module reaches the
    database only through get_session()/session_scope() rather than holding
    its own reference to `engine`/`SessionLocal` - both look the name up in
    this module's globals at call time, not at import time - so this
    reassignment takes effect immediately everywhere, including the
    background sync scheduler and LLM chat history, with no further wiring."""
    global engine, SessionLocal
    from app import models  # noqa: F401 - ensures models are registered on Base

    path = _db_path_for(db_file)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    init_db()


def create_empty_db(db_file: str) -> None:
    """Initializes a brand-new user's SQLite file with the current schema,
    using a throwaway engine so it does NOT disturb this process's currently
    active engine/session - for creating a user without switching into it."""
    from app import models  # noqa: F401 - ensures models are registered on Base

    path = _db_path_for(db_file)
    tmp_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    try:
        Base.metadata.create_all(bind=tmp_engine)
    finally:
        tmp_engine.dispose()


def session_for(db_file: str):
    """A one-off Session bound to a specific user's file, independent of the
    active engine - for seeding a newly created user's database without
    switching into it. Caller is responsible for commit/close."""
    path = _db_path_for(db_file)
    tmp_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    return sessionmaker(bind=tmp_engine, autoflush=False, expire_on_commit=False)()


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
