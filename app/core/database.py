"""Database engine, session factory, and the declarative base.

Uses the SQLAlchemy 2.0 import path (``sqlalchemy.orm.declarative_base``) rather
than the deprecated ``sqlalchemy.ext.declarative`` location.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

# Engine backed by the configured PostgreSQL URL. ``pool_pre_ping`` transparently
# recycles connections that the database may have dropped, which matters for a
# long-running scheduler process.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Session factory: one short-lived session per request / unit of work.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base shared by every ORM model.
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and guarantee it is closed afterwards.

    Designed for use as a FastAPI dependency via ``Depends(get_db)``.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
