from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import Base, SessionLocal, engine
from app.main import app
from app.seed import seed_users


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    assert str(engine.url.database).endswith("_test"), "Run the tests with `make test`."
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean_db(migrated_db: None) -> None:
    # consent_texts is reference data that only migrations write.
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name != "consent_texts")
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        seed_users(db)
        db.commit()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
