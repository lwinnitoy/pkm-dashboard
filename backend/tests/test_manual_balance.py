"""Manual-account balances: an owner-entered anchor, rolled forward by imports."""
from datetime import date, timedelta

import pytest

from app.imports.balance import refresh, roll_forward, set_anchor
from app.models import SOURCE_CSV, Account, BalanceSnapshot
from tests.factories import make_account, make_snapshot, make_transaction
from tests.test_imports import rbc_csv, row

ANCHOR = date(2026, 9, 1)


def manual(db, *, type: str = "depository", name: str = "RBC Chequing") -> Account:
    account = Account(source=SOURCE_CSV, name=name, type=type, currency="CAD")
    db.add(account)
    db.flush()
    return account


def spend(db, account: Account, amount: float, on: date) -> None:
    make_transaction(db, account=account, amount=amount, txn_date=on)


# --- Roll-forward ---------------------------------------------------------------


def test_chequing_balance_moves_with_transactions_after_the_anchor(db_session):
    chq = manual(db_session)
    spend(db_session, chq, 50.0, ANCHOR - timedelta(days=1))  # already in the anchor
    spend(db_session, chq, 50.0, ANCHOR)                        # same day: also already in it
    spend(db_session, chq, 30.0, ANCHOR + timedelta(days=1))    # purchase: money out
    spend(db_session, chq, -200.0, ANCHOR + timedelta(days=2))  # paycheque: money in

    set_anchor(db_session, chq, 1000.0, ANCHOR)

    assert chq.current_balance == 1170.0


def test_credit_card_balance_is_the_amount_owed(db_session):
    card = manual(db_session, type="credit", name="RBC Credit")
    spend(db_session, card, 40.0, ANCHOR + timedelta(days=1))    # purchase raises what's owed
    spend(db_session, card, -300.0, ANCHOR + timedelta(days=2))  # payment lowers it

    set_anchor(db_session, card, 500.0, ANCHOR)

    assert card.current_balance == 240.0


def test_without_an_anchor_nothing_is_derived(db_session):
    chq = manual(db_session)
    spend(db_session, chq, 30.0, ANCHOR)

    roll_forward(db_session, chq)
    refresh(db_session, chq)

    assert chq.current_balance is None
    assert db_session.query(BalanceSnapshot).count() == 0


def test_type_change_flips_the_sign(db_session):
    """An account first imported as chequing and corrected to a credit card."""
    acct = manual(db_session)
    spend(db_session, acct, 100.0, ANCHOR + timedelta(days=1))
    set_anchor(db_session, acct, 500.0, ANCHOR)
    assert acct.current_balance == 400.0

    acct.type = "credit"
    refresh(db_session, acct)

    assert acct.current_balance == 600.0


# --- Snapshots ------------------------------------------------------------------


def test_setting_a_balance_refreshes_only_todays_snapshot_for_that_account(db_session):
    chq = manual(db_session)
    other = make_account(db_session, current_balance=75.0)
    yesterday = date.today() - timedelta(days=1)
    make_snapshot(db_session, account=chq, on=yesterday, balance=None)
    make_snapshot(db_session, account=other, on=date.today(), balance=75.0)

    set_anchor(db_session, chq, 1000.0, date.today())
    db_session.flush()

    snaps = {(s.account_id, s.date): s.balance for s in db_session.query(BalanceSnapshot)}
    assert snaps == {
        (chq.id, yesterday): None,  # history untouched
        (chq.id, date.today()): 1000.0,
        (other.id, date.today()): 75.0,
    }


# --- API --------------------------------------------------------------------------


def test_patch_sets_balance_and_net_worth_picks_it_up(client, db_session):
    card = manual(db_session, type="credit", name="RBC Credit")
    spend(db_session, card, 25.0, date.today())
    db_session.commit()

    res = client.patch(
        f"/api/imports/accounts/{card.id}",
        json={"balance": 568.69, "balance_as_of": (date.today() - timedelta(days=1)).isoformat()},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["current_balance"] == 593.69
    assert body["balance_anchor_date"] == (date.today() - timedelta(days=1)).isoformat()
    latest = client.get("/api/finance/net-worth").json()[-1]
    assert latest["liabilities"] == 593.69


def test_patch_defaults_as_of_to_today_and_null_clears(client, db_session):
    chq = manual(db_session)
    db_session.commit()

    set_res = client.patch(f"/api/imports/accounts/{chq.id}", json={"balance": 1234.5})
    assert set_res.json()["balance_anchor_date"] == date.today().isoformat()

    cleared = client.patch(f"/api/imports/accounts/{chq.id}", json={"balance": None}).json()
    assert cleared["current_balance"] is None
    assert cleared["balance_anchor_date"] is None


def test_patch_rejects_plaid_accounts_and_as_of_without_balance(client, db_session):
    plaid_acct = make_account(db_session)
    chq = manual(db_session)
    db_session.commit()

    assert client.patch(
        f"/api/imports/accounts/{plaid_acct.id}", json={"balance": 10}
    ).status_code == 400
    assert client.patch(
        f"/api/imports/accounts/{chq.id}", json={"balance_as_of": "2026-09-01"}
    ).status_code == 422


def test_create_with_opening_balance_anchors_it_today(client):
    res = client.post(
        "/api/imports/accounts",
        json={"name": "RBC Nomi Savings", "type": "depository", "subtype": "savings",
              "current_balance": 300},
    )

    assert res.status_code == 201
    assert res.json()["current_balance"] == 300
    assert res.json()["balance_anchor_date"] == date.today().isoformat()


@pytest.mark.parametrize(
    "rows, expected",
    [
        # Newer than the anchor: a $40 purchase lowers the chequing balance.
        ([row("9/10/2026", "GROCER", "-40.00")], 960.0),
        # Back-filling an older statement must not change it.
        ([row("8/10/2026", "GROCER", "-40.00")], 1000.0),
    ],
)
def test_import_commit_rolls_the_balance_forward(client, db_session, rows, expected):
    chq = manual(db_session)
    set_anchor(db_session, chq, 1000.0, ANCHOR)
    db_session.commit()

    res = client.post(
        "/api/imports/commit",
        files={"file": ("rbc.csv", rbc_csv(*rows), "text/csv")},
        data={"account_id": str(chq.id), "preset": "rbc"},
    )

    assert res.status_code == 200
    db_session.expire_all()
    assert db_session.get(Account, chq.id).current_balance == expected
