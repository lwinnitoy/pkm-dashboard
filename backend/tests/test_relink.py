"""Re-linking a bank must not duplicate it.

Plaid mints a fresh item_id *and* fresh account_ids every time you go through
Link, so a reconnect looks like a brand-new institution unless it's matched on
something stable. Wealthsimple showed up twice (two Cash, two TFSA) because of
exactly this.
"""
from datetime import date
from types import SimpleNamespace

import pytest

import app.routers.plaid as plaid_router
from app.models import Account, BalanceSnapshot, ImportBatch, PlaidItem, Transaction
from tests.factories import make_account, make_snapshot, make_transaction

WEALTHSIMPLE = "ins_wealthsimple"


def _account(account_id, name="Cash", mask="1234", subtype="checking", balance=986.75):
    return SimpleNamespace(
        account_id=account_id,
        name=name,
        mask=mask,
        official_name=None,
        type="depository",
        subtype=subtype,
        balances=SimpleNamespace(current=balance, iso_currency_code="CAD"),
    )


class FakeLinkClient:
    """Each exchange returns a *new* item_id and new account_ids, like Plaid."""

    def __init__(self):
        self.link_count = 0
        self.accounts = []

    def item_public_token_exchange(self, request):
        self.link_count += 1
        return SimpleNamespace(
            access_token=f"access-{self.link_count}", item_id=f"item-{self.link_count}"
        )

    def accounts_get(self, request):
        suffix = self.link_count
        return SimpleNamespace(
            accounts=[
                _account(f"{a.account_id}-link{suffix}", a.name, a.mask, a.subtype)
                for a in self.accounts
            ]
        )


@pytest.fixture()
def link_client(monkeypatch):
    client = FakeLinkClient()
    client.accounts = [
        _account("cash", "Cash", "1234", "checking"),
        _account("tfsa", "TFSA", "5678", "tfsa"),
    ]
    monkeypatch.setattr(plaid_router, "get_plaid_client", lambda: client)
    return client


def _link(client, institution_id=WEALTHSIMPLE):
    return client.post(
        "/api/plaid/exchange-token",
        json={
            "public_token": "public-abc",
            "institution_name": "Wealthsimple",
            "institution_id": institution_id,
        },
    )


def test_relinking_the_same_bank_does_not_duplicate_its_accounts(
    client, db_session, link_client
):
    _link(client)
    _link(client)  # user reconnects; Plaid hands back all-new ids

    assert db_session.query(PlaidItem).count() == 1
    assert db_session.query(Account).count() == 2
    assert {a.name for a in db_session.query(Account)} == {"Cash", "TFSA"}


def test_relinking_rebinds_the_existing_rows_to_the_new_plaid_ids(
    client, db_session, link_client
):
    _link(client)
    cash = db_session.query(Account).filter_by(name="Cash").one()
    original_row_id, first_plaid_id = cash.id, cash.plaid_account_id

    _link(client)
    db_session.expire_all()
    cash = db_session.query(Account).filter_by(name="Cash").one()

    assert cash.id == original_row_id  # same row, so history survives
    assert cash.plaid_account_id != first_plaid_id  # pointed at the new Plaid id


def test_transaction_history_survives_a_relink(client, db_session, link_client):
    _link(client)
    cash = db_session.query(Account).filter_by(name="Cash").one()
    make_transaction(db_session, account=cash, amount=12.50, name="COFFEE")
    db_session.commit()

    _link(client)
    db_session.expire_all()

    assert db_session.query(Transaction).count() == 1
    assert db_session.query(Transaction).one().account_id == cash.id


def test_a_genuinely_different_bank_still_links_separately(
    client, db_session, link_client
):
    _link(client)
    _link(client, institution_id="ins_other_bank")

    assert db_session.query(PlaidItem).count() == 2


def test_relink_resets_the_cursor_since_transaction_ids_changed(
    client, db_session, link_client
):
    _link(client)
    item = db_session.query(PlaidItem).one()
    item.transactions_cursor = "cursor-from-the-old-item"
    db_session.commit()

    _link(client)
    db_session.expire_all()

    assert db_session.query(PlaidItem).one().transactions_cursor is None


# ---- deletion ----


def test_deleting_an_account_removes_its_dependent_rows(client, db_session):
    account = make_account(db_session)
    make_transaction(db_session, account=account, amount=5.0)
    make_snapshot(db_session, account=account, on=date.today(), balance=10.0)
    db_session.add(
        ImportBatch(
            account_id=account.id,
            filename="x.csv",
            preset="rbc",
            period_start=date.today(),
            period_end=date.today(),
        )
    )
    db_session.commit()

    assert client.delete(f"/api/finance/accounts/{account.id}").status_code == 204

    assert db_session.query(Account).count() == 0
    assert db_session.query(Transaction).count() == 0
    assert db_session.query(BalanceSnapshot).count() == 0
    assert db_session.query(ImportBatch).count() == 0


def test_removing_the_last_account_drops_the_empty_item(client, db_session):
    account = make_account(db_session)
    db_session.commit()

    client.delete(f"/api/finance/accounts/{account.id}")

    assert db_session.query(PlaidItem).count() == 0


def test_an_item_with_accounts_left_is_kept(client, db_session, link_client):
    _link(client)
    cash = db_session.query(Account).filter_by(name="Cash").one()

    client.delete(f"/api/finance/accounts/{cash.id}")
    db_session.expire_all()

    assert db_session.query(PlaidItem).count() == 1
    assert db_session.query(Account).count() == 1


def test_deleting_a_missing_account_is_a_404(client, db_session):
    assert client.delete("/api/finance/accounts/9999").status_code == 404
