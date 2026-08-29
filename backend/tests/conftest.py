import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.repositories.accounts import AccountRepository
from app.repositories.categories import CategoryRepository


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = Session()
    CategoryRepository(s).ensure_defaults()
    AccountRepository(s).ensure_default()
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def sheets():
    from tests.fakes import FakeGoogleSheetsService
    return FakeGoogleSheetsService()
