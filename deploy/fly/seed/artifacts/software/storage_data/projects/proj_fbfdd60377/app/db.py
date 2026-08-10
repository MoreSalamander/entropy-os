"""Database wiring: SQLite via SQLAlchemy, session per request."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")

engine = create_engine(DATABASE_URL,
                       connect_args={"check_same_thread": False}
                       if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    """FastAPI dependency: one session per request, always closed."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from app import models  # noqa: F401 — models must import before create_all
    Base.metadata.create_all(engine)
