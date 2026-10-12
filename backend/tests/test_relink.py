"""Re-linking a bank must not duplicate it.

Plaid mints a fresh item_id *and* fresh account_ids every time you go through
Link, so a reconnect looks like a brand-new institution unless it's matched on
something stable. Wealthsimple showed up twice (two Cash, two TFSA) because of
exactly this.
"""
from datetime import date
from types import SimpleNamespace

import pytest

import app.routers.finance as finance_router
import app.routers.plaid as plaid_router
from app.models import Account, BalanceSnapshot, ImportBatch, PlaidItem, Transaction
from tests.factories import make_account, make_snapshot, make_transaction

WEALTHSIMPLE = "ins_wealthsimple"


@pytest.fixture(autouse=True)
def plaid_removals(monkeypatch):
    """Access tokens the delete endpoint asked Plaid to remove (never the network)."""
    removed: list[str] = []
    stub = SimpleNamespace(item_remove=lambda req: removed.append(req.access_token))
    monkeypatch.setattr(finance_router, "get_plaid_client", lambda: stub)
    return removed


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
        self.sync_pages: dict = {}  # access_token -> one complete sync page
        self.removed_tokens: list[str] = []

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

    def transactions_sync(self, request):
        return self.sync_pages[request.access_token]

    def item_remove(self, request):
        self.removed_tokens.append(request.access_token)


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


def test_deleting_an_imported_account_whose_transactions_reference_its_batch(
    client, db_session
):
    account = make_account(db_session)
    batch = ImportBatch(
        account_id=account.id,
        filename="x.csv",
        preset="rbc",
        period_start=date.today(),
        period_end=date.today(),
    )
    db_session.add(batch)
    db_session.flush()
    txn = make_transaction(db_session, account=account, amount=5.0)
    txn.import_batch_id = batch.id
    db_session.commit()

    assert client.delete(f"/api/finance/accounts/{account.id}").status_code == 204

    assert db_session.query(Transaction).count() == 0
    assert db_session.query(ImportBatch).count() == 0


def test_removing_the_last_account_drops_the_empty_item(client, db_session, plaid_removals):
    account = make_account(db_session)
    db_session.commit()

    client.delete(f"/api/finance/accounts/{account.id}")

    assert db_session.query(PlaidItem).count() == 0
    assert plaid_removals == ["tok-item-for-acct-1"]  # and released at Plaid


def test_an_item_with_accounts_left_is_kept(client, db_session, link_client):
    _link(client)
    cash = db_session.query(Account).filter_by(name="Cash").one()

    client.delete(f"/api/finance/accounts/{cash.id}")
    db_session.expire_all()

    assert db_session.query(PlaidItem).count() == 1
    assert db_session.query(Account).count() == 1


def test_deleting_a_missing_account_is_a_404(client, db_session):
    assert client.delete("/api/finance/accounts/9999").status_code == 404


# ---- re-walk after a re-link ----


def _plaid_txn(txn_id, account_id, amount, name, pending=False, on=date(2026, 9, 1)):
    return SimpleNamespace(
        transaction_id=txn_id,
        account_id=account_id,
        date=on,
        name=name,
        merchant_name=None,
        amount=amount,
        iso_currency_code="CAD",
        personal_finance_category=SimpleNamespace(primary="FOOD_AND_DRINK", detailed=None),
        pending=pending,
    )


def _page(*txns):
    return SimpleNamespace(added=list(txns), modified=[], removed=[], next_cursor="c", has_more=False)


def test_resyncing_after_a_relink_does_not_duplicate_history(client, db_session, link_client):
    """Plaid's new Item re-sends every transaction under new ids; each one must
    land on the row we already have, not beside it."""
    _link(client)
    link_client.sync_pages["access-1"] = _page(
        _plaid_txn("old-1", "cash-link1", 4.50, "COFFEE"),
        _plaid_txn("old-2", "cash-link1", 4.50, "COFFEE"),  # a genuine second coffee
        _plaid_txn("old-3", "cash-link1", 60.00, "GROCER"),
        _plaid_txn("old-p", "cash-link1", 9.99, "PENDING THING", pending=True),
    )
    client.post("/api/plaid/sync")
    assert db_session.query(Transaction).count() == 4

    _link(client)
    link_client.sync_pages["access-2"] = _page(
        _plaid_txn("new-1", "cash-link2", 4.50, "COFFEE"),
        _plaid_txn("new-2", "cash-link2", 4.50, "COFFEE"),
        _plaid_txn("new-3", "cash-link2", 60.00, "GROCER"),
        # The pending charge has since posted, a day later.
        _plaid_txn("new-p", "cash-link2", 9.99, "PENDING THING", on=date(2026, 9, 2)),
    )
    resp = client.post("/api/plaid/sync")

    assert resp.json()["added"] == 4
    db_session.expire_all()
    rows = db_session.query(Transaction).all()
    assert len(rows) == 4
    assert {t.plaid_transaction_id for t in rows} == {"new-1", "new-2", "new-3", "new-p"}
    assert not any(t.pending for t in rows)


def test_history_older_than_the_new_items_window_is_kept(client, db_session, link_client):
    _link(client)
    cash = db_session.query(Account).filter_by(name="Cash").one()
    make_transaction(db_session, account=cash, amount=7.0, name="OLD", txn_date=date(2023, 1, 5))
    db_session.commit()

    _link(client)
    link_client.sync_pages["access-2"] = _page()
    client.post("/api/plaid/sync")

    db_session.expire_all()
    old = db_session.query(Transaction).one()
    assert old.name == "OLD"
    assert old.plaid_transaction_id is None  # detached, still counted


def test_relink_removes_the_replaced_item_at_plaid(client, db_session, link_client):
    _link(client)
    _link(client)

    assert link_client.removed_tokens == ["access-1"]



def test_a_second_login_at_the_same_bank_stays_separate(client, db_session, link_client):
    """Personal and joint logins share an institution id but no accounts."""
    _link(client)
    link_client.accounts = [_account("joint", "Joint Chequing", "9999", "checking")]
    _link(client)

    assert db_session.query(PlaidItem).count() == 2
    assert db_session.query(Account).count() == 3
    assert link_client.removed_tokens == []  # nothing was replaced
