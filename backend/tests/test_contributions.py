"""Monthly contribution rate behind the Goals page's "current direction"."""
from datetime import date, timedelta

from app.investments.contributions import contribution_rate
from app.models import InvestmentTransaction
from tests.factories import make_account

TODAY = date(2026, 10, 1)
_seq = 0


def itx(db, account, *, days_ago, type, subtype, amount):
    global _seq
    _seq += 1
    db.add(InvestmentTransaction(
        account_id=account.id, plaid_investment_transaction_id=f"it-{_seq}",
        date=TODAY - timedelta(days=days_ago), type=type, subtype=subtype, amount=amount,
    ))
    db.flush()


def test_nets_deposits_and_withdrawals_over_the_history_window(db_session):
    tfsa = make_account(db_session, type="investment", name="TFSA")
    for days_ago in (5, 35, 65, 95, 125, 155):  # ~$500 a month for six months
        itx(db_session, tfsa, days_ago=days_ago, type="cash", subtype="deposit", amount=-500)
    itx(db_session, tfsa, days_ago=40, type="cash", subtype="withdrawal", amount=300)
    # Growth, not saving: none of these count.
    itx(db_session, tfsa, days_ago=10, type="buy", subtype="buy", amount=480)
    itx(db_session, tfsa, days_ago=181, type="cash", subtype="dividend", amount=-20)

    rate = contribution_rate(db_session, [tfsa.id], today=TODAY)

    assert rate.net_total == 2700.0
    assert rate.count == 7
    assert rate.history_days == 182
    assert rate.monthly == round(2700 / (182 / (365.25 / 12)), 2)


def test_too_little_history_gives_no_monthly_rate(db_session):
    """A fresh link often returns about a week of history; that isn't a rate."""
    tfsa = make_account(db_session, type="investment", name="TFSA")
    itx(db_session, tfsa, days_ago=3, type="cash", subtype="contribution", amount=-1000)

    rate = contribution_rate(db_session, [tfsa.id], today=TODAY)

    assert rate.monthly is None
    assert rate.net_total == 1000.0
    assert rate.history_days == 4


def test_direction_endpoint(client, db_session):
    tfsa = make_account(db_session, type="investment", name="TFSA", current_balance=20960.59)
    db_session.commit()

    body = client.get("/api/investments/direction").json()

    assert body["total_value"] == 20960.59
    assert body["account_names"] == ["TFSA"]
    assert body["monthly_contribution"] is None
    assert body["history_days"] == 0
