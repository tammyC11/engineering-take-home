import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://diary:diary@localhost:5432/diary"
)

# Keep SQL parameters (notes, moods) out of error messages, which can end up in logs (O.Log_4).
engine = create_engine(DATABASE_URL, hide_parameters=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
