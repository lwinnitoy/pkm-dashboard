"""The daily job (`python -m app.jobs`): every step runs, whatever fails first."""
from datetime import date

import pytest

import app.jobs as jobs
import app.snapshots as snapshots
from app.models import Account, BalanceSnapshot
from tests.factories import make_account


@pytest.fixture()
def job_db(monkeypatch, TestingSessionLocal):
    monkeypatch.setattr(jobs, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(snapshots, "SessionLocal", TestingSessionLocal)


def test_imported_accounts_get_snapshots_with_nothing_linked(job_db, db_session):
    account = Account(name="RBC Chequing", type="depository", source="csv", current_balance=1200.0)
    db_session.add(account)
    db_session.commit()

    assert jobs.run() is True

    snap = db_session.query(BalanceSnapshot).filter_by(account_id=account.id).one()
    assert (snap.date, snap.balance) == (date.today(), 1200.0)


def test_a_failing_sync_still_snapshots_and_reports_failure(job_db, db_session, monkeypatch):
    make_account(db_session, current_balance=50.0)
    db_session.commit()

    def boom(db):
        raise RuntimeError("plaid is down")

    monkeypatch.setattr(jobs, "sync_all_items", boom)
    monkeypatch.setattr(jobs, "sync_all_investments", lambda db: {})
    monkeypatch.setattr(snapshots, "refresh_balances", lambda db: None)

    assert jobs.run() is False
    assert db_session.query(BalanceSnapshot).count() == 1
