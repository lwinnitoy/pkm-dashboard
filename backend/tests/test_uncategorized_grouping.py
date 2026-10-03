"""NULL and the literal "Uncategorized" are one bucket in every spending total.

Sync and imports write the literal, but older rows can be NULL. Grouped by the raw
column they came back as two "Uncategorized" entries, and the endpoints that key a
dict by category name silently kept only one of them.
"""
from datetime import date

from tests.factories import make_account, make_transaction


def _seed(db):
    acct = make_account(db)
    make_transaction(db, account=acct, amount=10.0, category=None)
    make_transaction(db, account=acct, amount=25.0, category="Uncategorized")
    make_transaction(db, account=acct, amount=5.0, category="Dining")
    db.commit()


def test_summary_reports_one_uncategorized_bucket(client, db_session):
    _seed(db_session)
    cats = client.get("/api/finance/summary").json()["by_category"]
    assert [(c["category"], c["total"], c["count"]) for c in cats] == [
        ("Uncategorized", 35.0, 2),
        ("Dining", 5.0, 1),
    ]


def test_comparison_counts_both_and_includes_today(client, db_session):
    _seed(db_session)  # all dated today, which the current window must include
    rows = {r["category"]: r["current"] for r in client.get("/api/finance/category-comparison").json()}
    assert rows == {"Uncategorized": 35.0, "Dining": 5.0}


def test_budget_status_counts_both(client, db_session):
    _seed(db_session)
    status = client.get(
        "/api/finance/budgets/status", params={"month": date.today().strftime("%Y-%m")}
    ).json()
    spent = {i["category"]: i["spent"] for i in status["items"]}
    assert spent["Uncategorized"] == 35.0
    assert status["total_spent"] == 40.0
