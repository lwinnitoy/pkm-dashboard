"""Refunds net against spending, the same way in every view.

Before, the trend counted a refund as income while the summary and budgets ignored
it, so the pages disagreed about the same month."""
from datetime import date

from tests.factories import make_account, make_transaction

TODAY = date.today()


def _seed(db_session):
    acct = make_account(db_session)
    make_transaction(db_session, account=acct, amount=100.0, category="Shopping", name="JACKET")
    make_transaction(db_session, account=acct, amount=-100.0, category="Shopping", name="JACKET")
    make_transaction(db_session, account=acct, amount=40.0, category="Dining", name="CAFE")
    make_transaction(db_session, account=acct, amount=-10.0, category="Dining", name="CAFE")
    # A deposit nobody categorized: a paycheque, not a negative expense.
    make_transaction(db_session, account=acct, amount=-2000.0, category="Uncategorized", name="PAYROLL")
    make_transaction(db_session, account=acct, amount=-500.0, category="Income", name="SALARY")
    make_transaction(db_session, account=acct, amount=300.0, category="Transfers", name="CARD PAYMENT")
    db_session.commit()


def test_summary_nets_refunds_and_drops_fully_refunded_categories(client, db_session):
    _seed(db_session)

    body = client.get("/api/finance/summary?period=30").json()

    assert body["total_spent"] == 30.0
    assert body["transaction_count"] == 2  # purchases, not refunds
    assert {c["category"]: c["total"] for c in body["by_category"]} == {"Dining": 30.0}


def test_budgets_count_spending_net_of_refunds(client, db_session):
    _seed(db_session)
    client.post("/api/finance/budgets", json={"category": "Shopping", "monthly_limit": 200})

    items = {i["category"]: i for i in client.get("/api/finance/budgets/status").json()["items"]}

    assert items["Shopping"]["spent"] == 0.0
    assert items["Dining"]["spent"] == 30.0


def test_trend_agrees_with_the_summary(client, db_session):
    _seed(db_session)

    trend = client.get("/api/finance/spending-trend?period=30&granularity=month").json()
    summary = client.get("/api/finance/summary?period=30").json()

    assert round(sum(p["spent"] for p in trend), 2) == summary["total_spent"]
    # Income is the Income category plus the uncategorized deposit; refunds and
    # the transfer are not income.
    assert round(sum(p["income"] for p in trend), 2) == 2500.0


def test_merchants_and_comparison_net_refunds(client, db_session):
    _seed(db_session)

    merchants = client.get("/api/finance/top-merchants?period=30").json()
    comparison = client.get("/api/finance/category-comparison?days=30").json()

    assert [(m["merchant"], m["total"]) for m in merchants] == [("CAFE", 30.0)]
    assert {c["category"]: c["current"] for c in comparison}["Shopping"] == 0.0
