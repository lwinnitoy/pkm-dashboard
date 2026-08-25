"""Plaid router: exchange-token and sync, with a fully stubbed Plaid client.

No real network calls happen — ``get_plaid_client`` (as imported into the router
module) is monkeypatched to return a fake client whose methods return simple
namespace objects mirroring the plaid-python SDK response shapes.
"""
from datetime import date
from types import SimpleNamespace

import pytest

import app.routers.plaid as plaid_router
from app.models import Account, PlaidItem, Transaction


def _account(account_id, name="Checking", type_="depository", balance=100.0):
    return SimpleNamespace(
        account_id=account_id,
        name=name,
        official_name=None,
        type=type_,
        subtype=None,
        balances=SimpleNamespace(current=balance, iso_currency_code="USD"),
    )


def _txn(txn_id, account_id, amount, name="Coffee", category="FOOD_AND_DRINK"):
    return SimpleNamespace(
        transaction_id=txn_id,
        account_id=account_id,
        date=date.today(),
        name=name,
        merchant_name=name,
        amount=amount,
        iso_currency_code="USD",
        personal_finance_category=SimpleNamespace(primary=category),
        pending=False,
    )


class FakePlaidClient:
    """Records calls and returns canned, cursor-aware sync pages."""

    def __init__(self, *, item_id="item-abc", access_token="access-xyz", accounts=None):
        self.item_id = item_id
        self.access_token = access_token
        self._accounts = accounts if accounts is not None else [_account("acct-1")]
        # cursor -> page. ``None`` (no cursor) is the first page.
        self.sync_pages: dict = {}

    def item_public_token_exchange(self, request):
        return SimpleNamespace(access_token=self.access_token, item_id=self.item_id)

    def accounts_get(self, request):
        return SimpleNamespace(accounts=self._accounts)

    def transactions_sync(self, request):
        cursor = getattr(request, "cursor", None)
        return self.sync_pages[cursor]


def _sync_page(*, added=(), modified=(), removed=(), next_cursor, has_more=False):
    return SimpleNamespace(
        added=list(added),
        modified=list(modified),
        removed=[SimpleNamespace(transaction_id=r) for r in removed],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@pytest.fixture()
def fake_client(monkeypatch):
    client = FakePlaidClient()
    monkeypatch.setattr(plaid_router, "get_plaid_client", lambda: client)
    return client


# --------------------------------------------------------------------------- #
# exchange-token                                                               #
# --------------------------------------------------------------------------- #
def test_exchange_token_creates_item_and_accounts(client, fake_client, db_session):
    fake_client._accounts = [_account("acct-1"), _account("acct-2", name="Savings")]

    resp = client.post(
        "/api/plaid/exchange-token",
        json={"public_token": "public-abc", "institution_name": "Test Bank"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"item_id": "item-abc", "accounts_linked": 2}

    item = db_session.query(PlaidItem).filter_by(item_id="item-abc").one()
    assert item.institution_name == "Test Bank"
    assert item.access_token == "access-xyz"  # decrypts back to plaintext
    assert db_session.query(Account).count() == 2


def test_exchange_token_upserts_existing_item(client, fake_client, db_session):
    # First link.
    client.post("/api/plaid/exchange-token", json={"public_token": "public-1"})
    # Same item_id, refreshed token; balances updated, no duplicate accounts.
    fake_client.access_token = "access-rotated"
    fake_client._accounts = [_account("acct-1", balance=250.0)]
    resp = client.post("/api/plaid/exchange-token", json={"public_token": "public-2"})
    assert resp.status_code == 200

    assert db_session.query(PlaidItem).count() == 1
    assert db_session.query(Account).count() == 1
    item = db_session.query(PlaidItem).one()
    assert item.access_token == "access-rotated"
    assert db_session.query(Account).one().current_balance == 250.0


# --------------------------------------------------------------------------- #
# sync                                                                         #
# --------------------------------------------------------------------------- #
def test_sync_requires_linked_item(client, fake_client):
    resp = client.post("/api/plaid/sync")
    assert resp.status_code == 400


def test_sync_applies_added_modified_removed_and_advances_cursor(
    client, fake_client, db_session
):
    # Link first so there's an item + account to attach transactions to.
    client.post("/api/plaid/exchange-token", json={"public_token": "public-abc"})

    # First sync: one page adds two transactions, cursor -> "cursor-1".
    fake_client.sync_pages = {
        None: _sync_page(
            added=[
                _txn("t1", "acct-1", 12.50),
                _txn("t2", "acct-1", 30.00),
            ],
            next_cursor="cursor-1",
            has_more=False,
        )
    }
    resp = client.post("/api/plaid/sync")
    assert resp.status_code == 200
    assert resp.json() == {"added": 2, "modified": 0, "removed": 0}
    assert db_session.query(Transaction).count() == 2

    item = db_session.query(PlaidItem).one()
    db_session.refresh(item)
    assert item.transactions_cursor == "cursor-1"  # cursor advanced & persisted

    # Second sync resumes from "cursor-1": modify t1, remove t2, cursor -> "cursor-2".
    fake_client.sync_pages = {
        "cursor-1": _sync_page(
            modified=[_txn("t1", "acct-1", 99.99, name="Updated")],
            removed=["t2"],
            next_cursor="cursor-2",
            has_more=False,
        )
    }
    resp = client.post("/api/plaid/sync")
    assert resp.json() == {"added": 0, "modified": 1, "removed": 1}

    txns = db_session.query(Transaction).all()
    assert len(txns) == 1  # t2 removed
    assert txns[0].plaid_transaction_id == "t1"
    assert txns[0].amount == 99.99  # t1 modified

    db_session.refresh(item)
    assert item.transactions_cursor == "cursor-2"


def test_sync_paginates_when_has_more(client, fake_client, db_session):
    client.post("/api/plaid/exchange-token", json={"public_token": "public-abc"})
    fake_client.sync_pages = {
        None: _sync_page(
            added=[_txn("t1", "acct-1", 1.0)], next_cursor="c1", has_more=True
        ),
        "c1": _sync_page(
            added=[_txn("t2", "acct-1", 2.0)], next_cursor="c2", has_more=False
        ),
    }
    resp = client.post("/api/plaid/sync")
    assert resp.json()["added"] == 2
    assert db_session.query(Transaction).count() == 2
    assert db_session.query(PlaidItem).one().transactions_cursor == "c2"
