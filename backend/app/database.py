"""SQLAlchemy engine, session factory, and declarative Base."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()
DATABASE_URL = settings.sqlalchemy_url

_is_sqlite = DATABASE_URL.startswith("sqlite")

# check_same_thread is a SQLite-only requirement for use across threads (e.g. the scheduler).
connect_args = {"check_same_thread": False} if _is_sqlite else {}

# Serverless Postgres (e.g. Neon on Replit) suspends when idle and drops open
# connections; pool_pre_ping transparently discards a dead connection and opens a
# fresh one instead of failing the request (psycopg AdminShutdown / closed conn).
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=not _is_sqlite,
    pool_recycle=300 if not _is_sqlite else -1,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
