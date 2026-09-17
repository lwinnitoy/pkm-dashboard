"""Imported rows must land in the dashboard, and transfers must not inflate it.

Two failure modes these cover, both of which made imported data silently wrong:
a NULL category dropped rows out of every SQL spending total, and credit-card
payments counted as income on the card while the paying account counted the
same money as spending.
"""
from datetime import date, timedelta

from app.imports.categorize import looks_like_transfer, resolve_category
from app.models import SOURCE_CSV, Account, Transaction
from tests.factories import make_account, make_transaction

HEADER = '"Transaction Date","Description 1","Description 2","CAD$"\n'


def rbc_csv(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode()


def row(when: str, desc: str, amount: str) -> str:
    return f'"{when}","{desc}","","{amount}"\n'


def manual_account(db, name="RBC Mastercard", type_="credit") -> Account:
    account = Account(source=SOURCE_CSV, name=name, type=type_, currency="CAD")
    db.add(account)
    db.flush()
    return account


def recent(days_ago: int) -> str:
    d = date.today() - timedelta(days=days_ago)
    return f"{d.month}/{d.day}/{d.year}"


# ---- uncategorized rows must still count as spending ----


def test_uncategorized_transactions_are_counted_as_spending(client, db_session):
    """`category NOT IN (...)` is UNKNOWN for NULL, which silently dropped rows."""
    account = make_account(db_session)
    txn = make_transaction(db_session, account=account, amount=25.00, category=None)
    assert txn.category is None
    db_session.commit()

    summary = client.get("/api/finance/summary?period=365").json()

    assert summary["total_spent"] == 25.00
    assert summary["transaction_count"] == 1
    assert summary["by_category"][0]["category"] == "Uncategorized"


def test_uncategorized_rows_reach_merchants_and_budget_status(client, db_session):
    account = make_account(db_session)
    make_transaction(
        db_session, account=account, amount=40.00, category=None, name="SOME SHOP"
    )
    db_session.commit()

    assert client.get("/api/finance/top-merchants?period=365").json()[0]["total"] == 40.00
    status = client.get("/api/finance/budgets/status").json()
    assert status["total_spent"] == 40.00


def test_an_imported_file_shows_up_in_the_spending_summary(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    client.post(
        "/api/imports/commit",
        files={"file": ("r.csv", rbc_csv(row(recent(5), "SOME SHOP", "-40.00")), "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    )

    summary = client.get("/api/finance/summary?period=365").json()
    assert summary["total_spent"] == 40.00


# ---- transfers ----


def test_recognises_rbc_card_payments_as_transfers():
    assert looks_like_transfer("PAYMENT - THANK YOU / PAI EMENT - MERCI")
    assert looks_like_transfer("TRANSFER TO 1234567")
    assert looks_like_transfer("INTERAC E-TRANSFER")
    assert looks_like_transfer("MASTERCARD PAYMENT")


def test_does_not_mistake_ordinary_spending_for_a_transfer():
    for description in (
        "TIM HORTONS #1234 ANYTOWN",
        "SOME CO-OP GAS BAR ANYTOWN",
        "PAYMENT PROCESSING SERVICES INC",  # contains "payment"
        "TRANSFERWISE",                     # contains "transfer"
    ):
        assert not looks_like_transfer(description), description


def test_a_user_rule_overrides_transfer_detection(client, db_session):
    account = make_account(db_session)
    txn = make_transaction(db_session, account=account, amount=1.0, name="TRANSFER TO 123")
    client.patch(f"/api/finance/transactions/{txn.id}", json={"category": "Shopping"})
    db_session.commit()

    assert resolve_category(db_session, "TRANSFER TO 123") == "Shopping"


def test_imported_card_payments_are_categorized_as_transfers(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    data = rbc_csv(
        row(recent(5), "TIM HORTONS #1234 ANYTOWN", "-4.19"),
        row(recent(4), "PAYMENT - THANK YOU / PAI EMENT - MERCI", "565.50"),
    )

    preview = client.post(
        "/api/imports/preview",
        files={"file": ("r.csv", data, "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    ).json()
    assert preview["transfers"] == 1

    client.post(
        "/api/imports/commit",
        files={"file": ("r.csv", data, "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    )
    stored = {t.name: t.category for t in db_session.query(Transaction).all()}
    assert stored["PAYMENT - THANK YOU / PAI EMENT - MERCI"] == "Transfers"
    assert stored["TIM HORTONS #1234 ANYTOWN"] == "Uncategorized"


def test_a_card_payment_is_neither_spending_nor_income(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    client.post(
        "/api/imports/commit",
        files={
            "file": (
                "r.csv",
                rbc_csv(
                    row(recent(5), "TIM HORTONS", "-4.19"),
                    row(recent(4), "PAYMENT - THANK YOU / PAI EMENT - MERCI", "565.50"),
                ),
                "text/csv",
            )
        },
        data={"account_id": account.id, "preset": "rbc"},
    )

    trend = client.get("/api/finance/spending-trend?period=365&granularity=month").json()
    assert round(sum(p["spent"] for p in trend), 2) == 4.19
    assert round(sum(p["income"] for p in trend), 2) == 0.0  # not $565.50 of "income"


# ---- account type ----


def test_a_credit_account_can_be_created_so_net_worth_sees_a_debt(client, db_session):
    created = client.post(
        "/api/imports/accounts",
        json={"name": "RBC Mastercard", "type": "credit", "current_balance": 500.0},
    ).json()

    assert created["type"] == "credit"


def test_a_mistyped_manual_account_can_be_corrected(client, db_session):
    created = client.post("/api/imports/accounts", json={"name": "RBC Mastercard"}).json()
    assert created["type"] == "depository"  # the default that made this necessary

    fixed = client.patch(
        f"/api/imports/accounts/{created['id']}", json={"type": "credit"}
    ).json()

    assert fixed["type"] == "credit"
    assert client.get("/api/imports/coverage").json()[0]["account_type"] == "credit"


def test_plaid_accounts_are_not_editable_here(client, db_session):
    account = make_account(db_session)
    db_session.commit()

    response = client.patch(f"/api/imports/accounts/{account.id}", json={"type": "credit"})

    assert response.status_code == 400
