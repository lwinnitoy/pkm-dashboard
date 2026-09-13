"""Finance router: summary, spending-trend, net-worth, and goals endpoints.

Asserts Plaid's amount-sign convention throughout: positive = money out (spend),
negative = money in (income).
"""
from datetime import date, timedelta

from tests.factories import (
    make_account,
    make_holding,
    make_snapshot,
    make_transaction,
)


# --------------------------------------------------------------------------- #
# summary                                                                      #
# --------------------------------------------------------------------------- #
def test_summary_totals_and_by_category(client, db_session):
    acct = make_account(db_session)
    make_transaction(db_session, account=acct, amount=40.0, category="Dining")
    make_transaction(db_session, account=acct, amount=10.0, category="Dining")
    make_transaction(db_session, account=acct, amount=25.0, category="Groceries")
    # Income (negative) and Transfers must be excluded from "spent".
    make_transaction(db_session, account=acct, amount=-500.0, category="Income")
    make_transaction(db_session, account=acct, amount=75.0, category="Transfers")
    db_session.commit()

    resp = client.get("/api/finance/summary?period=30")
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_spent"] == 75.0  # 40 + 10 + 25, income & transfers excluded
    assert body["transaction_count"] == 3

    by_cat = {c["category"]: c for c in body["by_category"]}
    assert by_cat["Dining"]["total"] == 50.0
    assert by_cat["Dining"]["count"] == 2
    assert by_cat["Groceries"]["total"] == 25.0
    assert "Income" not in by_cat
    assert "Transfers" not in by_cat


def test_summary_excludes_transactions_outside_window(client, db_session):
    acct = make_account(db_session)
    make_transaction(db_session, account=acct, amount=100.0, txn_date=date.today())
    make_transaction(
        db_session, account=acct, amount=999.0, txn_date=date.today() - timedelta(days=90)
    )
    db_session.commit()

    resp = client.get("/api/finance/summary?period=30")
    assert resp.json()["total_spent"] == 100.0


# --------------------------------------------------------------------------- #
# spending-trend                                                               #
# --------------------------------------------------------------------------- #
def test_spending_trend_separates_income_and_spend(client, db_session):
    acct = make_account(db_session)
    today = date.today()
    # Spend (positive) and income (negative) in the same month bucket.
    make_transaction(db_session, account=acct, amount=60.0, category="Dining", txn_date=today)
    make_transaction(db_session, account=acct, amount=40.0, category="Groceries", txn_date=today)
    make_transaction(db_session, account=acct, amount=-500.0, category="Income", txn_date=today)
    db_session.commit()

    resp = client.get("/api/finance/spending-trend?period=90&granularity=month")
    assert resp.status_code == 200
    points = resp.json()
    assert len(points) == 1
    point = points[0]
    assert point["spent"] == 100.0  # 60 + 40
    assert point["income"] == 500.0  # magnitude of the -500 credit
    assert point["period_start"] == today.replace(day=1).isoformat()


# --------------------------------------------------------------------------- #
# net-worth                                                                    #
# --------------------------------------------------------------------------- #
def test_net_worth_empty_without_snapshots(client, db_session):
    make_account(db_session)
    db_session.commit()
    assert client.get("/api/finance/net-worth").json() == []


def test_net_worth_reflects_snapshots_and_liabilities(client, db_session):
    asset = make_account(db_session, plaid_account_id="a-asset", type="depository")
    credit = make_account(db_session, plaid_account_id="a-credit", type="credit")
    day = date.today() - timedelta(days=1)
    make_snapshot(db_session, account=asset, on=day, balance=1000.0)
    make_snapshot(db_session, account=credit, on=day, balance=200.0)
    db_session.commit()

    points = client.get("/api/finance/net-worth").json()
    assert len(points) == 1
    p = points[0]
    assert p["assets"] == 1000.0
    assert p["liabilities"] == 200.0  # credit balance is money owed
    assert p["net_worth"] == 800.0


def test_net_worth_folds_in_portfolio_on_latest_point(client, db_session):
    asset = make_account(db_session, plaid_account_id="a-asset", type="depository")
    day = date.today() - timedelta(days=1)
    make_snapshot(db_session, account=asset, on=day, balance=1000.0)

    inv = make_account(db_session, plaid_account_id="a-inv", type="investment")
    make_holding(db_session, account=inv, institution_value=5000.0)
    db_session.commit()

    points = client.get("/api/finance/net-worth").json()
    last = points[-1]
    assert last["assets"] == 6000.0  # 1000 snapshot + 5000 portfolio
    assert last["net_worth"] == 6000.0


# --------------------------------------------------------------------------- #
# goals CRUD + projection                                                      #
# --------------------------------------------------------------------------- #
def _goal_payload(**overrides) -> dict:
    payload = {
        "name": "Retirement",
        "target_amount": 100000.0,
        "target_date": (date.today() + timedelta(days=365 * 10)).isoformat(),
        "expected_annual_return": 0.06,
        "monthly_contribution": 500.0,
    }
    payload.update(overrides)
    return payload


def test_goal_create_list_patch_delete(client, db_session):
    # create
    created = client.post("/api/finance/goals", json=_goal_payload())
    assert created.status_code == 201
    goal = created.json()
    goal_id = goal["id"]
    assert goal["name"] == "Retirement"

    # list
    listed = client.get("/api/finance/goals")
    assert listed.status_code == 200
    assert any(g["id"] == goal_id for g in listed.json())

    # patch
    patched = client.patch(f"/api/finance/goals/{goal_id}", json={"target_amount": 50000.0})
    assert patched.status_code == 200
    assert patched.json()["target_amount"] == 50000.0

    # delete
    assert client.delete(f"/api/finance/goals/{goal_id}").status_code == 204
    assert client.get(f"/api/finance/goals/{goal_id}") .status_code in (404, 405)
    assert all(g["id"] != goal_id for g in client.get("/api/finance/goals").json())


def test_goal_patch_and_delete_404_when_missing(client):
    assert client.patch("/api/finance/goals/9999", json={"name": "x"}).status_code == 404
    assert client.delete("/api/finance/goals/9999").status_code == 404


def test_goal_projection_unavailable_without_investments(client, db_session):
    """No holdings -> current_value None -> projection fields stay None."""
    created = client.post("/api/finance/goals", json=_goal_payload())
    goal = created.json()
    assert goal["current_value"] is None
    assert goal["projected_value"] is None
    assert goal["on_track"] is None
    assert goal["required_monthly_contribution"] is None


def test_goal_projection_populated_with_investments(client, db_session):
    acct = make_account(db_session, type="investment")
    make_holding(db_session, account=acct, institution_value=200000.0)
    db_session.commit()

    # Target well below current value + growth => on track, no PMT needed.
    created = client.post(
        "/api/finance/goals",
        json=_goal_payload(target_amount=50000.0, monthly_contribution=0.0),
    )
    goal = created.json()
    assert goal["current_value"] == 200000.0
    assert goal["projected_value"] is not None
    assert goal["projected_value"] > 200000.0  # grew at 6%/yr
    assert goal["on_track"] is True
    assert goal["gap"] == round(goal["projected_value"] - 50000.0, 2)
    assert goal["required_monthly_contribution"] == 0.0


def test_goal_projection_requires_contribution_when_behind(client, db_session):
    acct = make_account(db_session, type="investment")
    make_holding(db_session, account=acct, institution_value=1000.0)
    db_session.commit()

    created = client.post(
        "/api/finance/goals",
        json=_goal_payload(target_amount=1_000_000.0, monthly_contribution=0.0),
    )
    goal = created.json()
    assert goal["on_track"] is False
    assert goal["required_monthly_contribution"] > 0
