"""Recategorization (merchant rules) and monthly budgets."""
from datetime import date

from app.categorization import rule_category
from app.models import Transaction
from tests.factories import make_account, make_transaction


# --------------------------------------------------------------------------- #
# recategorization → durable merchant rule                                     #
# --------------------------------------------------------------------------- #
def test_recategorize_creates_rule_and_reassigns_same_merchant(client, db_session):
    acct = make_account(db_session)
    t1 = make_transaction(db_session, account=acct, amount=5.0, category="Dining", merchant_name="Starbucks")
    t2 = make_transaction(db_session, account=acct, amount=6.0, category="Dining", merchant_name="Starbucks")
    other = make_transaction(db_session, account=acct, amount=7.0, category="Dining", merchant_name="Whole Foods")
    db_session.commit()

    resp = client.patch(f"/api/finance/transactions/{t1.id}", json={"category": "Coffee"})
    assert resp.status_code == 200
    assert resp.json()["category"] == "Coffee"

    db_session.expire_all()
    # The rule retroactively reassigned the other Starbucks txn, not Whole Foods.
    assert db_session.get(Transaction, t2.id).category == "Coffee"
    assert db_session.get(Transaction, other.id).category == "Dining"
    # And it persists as a rule (case/space-insensitive) for future syncs.
    assert rule_category(db_session, "  STARBUCKS ", None) == "Coffee"


def test_recategorize_missing_transaction_404(client, db_session):
    assert client.patch("/api/finance/transactions/999", json={"category": "X"}).status_code == 404


def test_list_categories_includes_used(client, db_session):
    acct = make_account(db_session)
    make_transaction(db_session, account=acct, amount=5.0, category="ZzzCustomCat")
    db_session.commit()
    cats = client.get("/api/finance/categories").json()
    assert "ZzzCustomCat" in cats


# --------------------------------------------------------------------------- #
# budgets                                                                      #
# --------------------------------------------------------------------------- #
def test_budget_upsert_is_idempotent_and_deletes(client, db_session):
    r1 = client.post("/api/finance/budgets", json={"category": "Dining", "monthly_limit": 100})
    bid = r1.json()["id"]
    r2 = client.post("/api/finance/budgets", json={"category": "Dining", "monthly_limit": 250})
    assert r2.json()["id"] == bid  # same row, updated in place
    assert r2.json()["monthly_limit"] == 250
    assert len(client.get("/api/finance/budgets").json()) == 1

    assert client.delete(f"/api/finance/budgets/{bid}").status_code == 204
    assert client.get("/api/finance/budgets").json() == []


def test_budget_status_spent_vs_limit_for_month(client, db_session):
    acct = make_account(db_session)
    first = date.today().replace(day=1)
    make_transaction(db_session, account=acct, amount=120.0, category="Dining", txn_date=first)
    make_transaction(db_session, account=acct, amount=30.0, category="Groceries", txn_date=first)
    # Income is excluded from budget spend.
    make_transaction(db_session, account=acct, amount=-500.0, category="Income", txn_date=first)
    db_session.commit()
    client.post("/api/finance/budgets", json={"category": "Dining", "monthly_limit": 100})

    month = first.strftime("%Y-%m")
    body = client.get(f"/api/finance/budgets/status?month={month}").json()
    items = {i["category"]: i for i in body["items"]}

    # Budgeted, over limit.
    assert items["Dining"]["limit"] == 100
    assert items["Dining"]["spent"] == 120
    assert items["Dining"]["remaining"] == -20
    assert items["Dining"]["pct"] == 120.0
    assert items["Dining"]["budget_id"] is not None
    # Spending with no budget shows up with a null limit for surfacing.
    assert items["Groceries"]["limit"] is None
    assert items["Groceries"]["spent"] == 30
    assert "Income" not in items
    assert body["total_limit"] == 100
    assert body["total_spent"] == 150


def test_budget_status_isolates_other_months(client, db_session):
    acct = make_account(db_session)
    make_transaction(db_session, account=acct, amount=200.0, category="Dining", txn_date=date(2020, 1, 15))
    db_session.commit()
    client.post("/api/finance/budgets", json={"category": "Dining", "monthly_limit": 100})

    body = client.get("/api/finance/budgets/status?month=2021-06").json()
    dining = next(i for i in body["items"] if i["category"] == "Dining")
    assert dining["spent"] == 0  # the 2020 txn is outside 2021-06
    assert body["total_spent"] == 0


def test_budget_status_rejects_bad_month(client, db_session):
    assert client.get("/api/finance/budgets/status?month=nope").status_code == 400
