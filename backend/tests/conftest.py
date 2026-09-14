"""Shared pytest fixtures.

Sets up a hermetic environment BEFORE the app is imported:
- a freshly generated Fernet key so ``app.crypto`` can encrypt/decrypt, and
- a throwaway on-disk SQLite ``DATABASE_URL`` so importing ``app.database`` never
  touches the developer's real ``pkm.db``.

Each test gets an isolated in-memory SQLite database (shared across connections
via a StaticPool) with all tables created, wired into the app through
``app.dependency_overrides[get_db]``. The real APScheduler is stubbed so the
lifespan never starts a background thread.
"""
import os
import sys
import tempfile
from pathlib import Path

# --- Environment must be configured before importing anything from ``app`` ---
# ``app.*`` uses ``from app...`` imports, so ``backend/`` (this file's parent's
# parent) has to be importable even when pytest runs from the repo root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from cryptography.fernet import Fernet  # noqa: E402

os.environ["SECRET_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
# Point the import-time engine at a throwaway temp file, never the real dev DB
# and never a stray file in the working tree. Tests themselves run against a
# per-test in-memory DB (see the fixtures below).
_IMPORT_DB = os.path.join(tempfile.mkdtemp(prefix="pkm-tests-"), "import.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_IMPORT_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.main as app_main  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _no_scheduler(monkeypatch):
    """Stop the lifespan from starting the real BackgroundScheduler in tests."""
    monkeypatch.setattr(app_main, "start_scheduler", lambda: None)
    monkeypatch.setattr(app_main, "shutdown_scheduler", lambda: None)


@pytest.fixture()
def db_engine():
    """A fresh in-memory SQLite engine with all tables, isolated per test.

    A StaticPool keeps a single underlying connection so the in-memory database
    is shared between the test's own session and the app's request sessions.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def TestingSessionLocal(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture()
def db_session(TestingSessionLocal):
    """A session for seeding data directly in tests."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(TestingSessionLocal):
    """A TestClient whose ``get_db`` dependency hits the per-test database."""

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
