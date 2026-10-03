"""Holding valuation (app/investments/valuation.py), through the endpoints that
expose it: the price fallback chain and its currency guard, account-balance
totals, unrealized gain, and the allocation basis.

The Wealthsimple tests replay the live link: Plaid reports price and value 0 for
every holding, while quantities, cost bases and the account balance are real.
"""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import app.routers.investments as investments_router
from app.investments.portfolio import get_portfolio_value
from app.models import Holding, InvestmentTransaction, Security
from tests.factories import make_account, make_item

_seq = 0


def _security(db, ticker, *, close_price=None, close_as_of=None, currency=None) -> Security:
    sec = Security(
        plaid_security_id=f"sec-{ticker}",
        ticker_symbol=ticker,
        name=f"{ticker} fund",
        close_price=close_price,
        close_price_as_of=close_as_of,
        currency=currency,
    )
    db.add(sec)
    db.flush()
    return sec


def _holding(
    db, account, security, *, quantity, cost_basis=None, price=0.0, value=0.0, currency="CAD"
) -> Holding:
    """Defaults to what Wealthsimple sends: institution price and value both 0."""
    holding = Holding(
        account_id=account.id,
        security_id=security.id,
        quantity=quantity,
        institution_price=price,
        institution_value=value,
        cost_basis=cost_basis,
        currency=currency,
    )
    db.add(holding)
    db.flush()
    return holding


def _trade(db, account, security, *, price, on, currency="CAD", type="buy", amount=None):
    global _seq
    _seq += 1
    txn = InvestmentTransaction(
        account_id=account.id,
        security_id=security.id,
        plaid_investment_transaction_id=f"inv-txn-{_seq}",
        date=on,
        name=f"{security.ticker_symbol} - {type}",
        price=price,
        amount=amount,
        type=type,
        currency=currency,
    )
    db.add(txn)
    db.flush()
    return txn


def _holdings(client) -> dict[str, dict]:
    return {h["ticker"]: h for h in client.get("/api/investments/holdings").json()}


def _wealthsimple_tfsa(db):
    tfsa = make_account(
        db, plaid_account_id="ws-tfsa", name="TFSA", type="investment", current_balance=20960.59
    )
    vergf = _security(db, "VERGF")
    xic = _security(db, "XIC")
    _holding(db, tfsa, vergf, quantity=40.1272, cost_basis=1870.17)
    _holding(db, tfsa, _security(db, "VFVXF"), quantity=55.5104, cost_basis=9603.68)
    _holding(db, tfsa, xic, quantity=71.9506, cost_basis=3899.25)
    _holding(db, tfsa, _security(db, "XEF"), quantity=79.1426, cost_basis=3921.37)
    # Dividend reinvestments are buys. Plaid labels VEE's USD (it resolves the
    # security to the US listing) though the holding is CAD.
    _trade(db, tfsa, xic, price=56.41, on=date(2026, 9, 30))
    _trade(db, tfsa, vergf, price=50.7332, on=date(2026, 9, 28), currency="USD")
    # The dividends themselves: cash in, price 0.
    _trade(db, tfsa, xic, price=0.0, on=date(2026, 9, 29), type="cash", amount=-20.40)
    _trade(db, tfsa, vergf, price=0.0, on=date(2026, 9, 27), type="cash", amount=-12.65)
    db.commit()
    return tfsa


# --------------------------------------------------------------------------- #
# the price fallback chain                                                     #
# --------------------------------------------------------------------------- #
def test_institution_price_is_used_when_plaid_reports_one(client, db_session):
    acct = make_account(db_session, type="investment")
    h = _holding(db_session, acct, _security(db_session, "VOO"), quantity=10, price=50.0, value=500.0)
    h.updated_at = datetime(2026, 9, 29, 21, 0)  # last synced
    db_session.commit()

    voo = _holdings(client)["VOO"]
    assert (voo["price"], voo["value"]) == (50.0, 500.0)
    assert voo["price_source"] == "institution"
    assert voo["price_as_of"] == "2026-09-29"


def test_a_resync_moves_the_institution_price_as_of_date(client, db_session, monkeypatch):
    """The as-of date is the last sync's, not the day the holding first appeared."""
    item = make_item(db_session, item_id="ws-1", name="Wealthsimple")
    acct = make_account(db_session, item=item, plaid_account_id="tfsa-1", type="investment")
    sec = _security(db_session, "XIC")
    h = _holding(db_session, acct, sec, quantity=71.9506, price=56.0, value=4029.23)
    h.updated_at = datetime(2025, 1, 1)
    db_session.commit()

    plaid = SimpleNamespace(
        investments_holdings_get=lambda request: SimpleNamespace(
            securities=[SimpleNamespace(security_id=sec.plaid_security_id, ticker_symbol="XIC")],
            holdings=[
                SimpleNamespace(
                    account_id="tfsa-1",
                    security_id=sec.plaid_security_id,
                    quantity=71.9506,
                    institution_price=56.41,
                    institution_value=4058.73,
                )
            ],
        ),
        investments_transactions_get=lambda request: SimpleNamespace(
            total_investment_transactions=0, securities=[], investment_transactions=[]
        ),
    )
    monkeypatch.setattr(investments_router, "get_plaid_client", lambda: plaid)
    assert client.post("/api/investments/sync").json()["holdings"] == 1

    xic = _holdings(client)["XIC"]
    assert xic["price"] == 56.41
    assert date.fromisoformat(xic["price_as_of"]) >= date.today() - timedelta(days=1)


def test_institution_value_alone_still_prices_the_holding(client, db_session):
    acct = make_account(db_session, type="investment")
    _holding(db_session, acct, _security(db_session, "VOO"), quantity=4, price=0.0, value=500.0)
    db_session.commit()

    voo = _holdings(client)["VOO"]
    assert voo["value"] == 500.0  # taken as given, not re-derived
    assert voo["price"] == 125.0
    assert voo["price_source"] == "institution"


def test_zero_institution_price_falls_back_to_close_price(client, db_session):
    acct = make_account(db_session, type="investment")
    sec = _security(
        db_session, "XEF", close_price=40.0, close_as_of=date(2026, 9, 29), currency="CAD"
    )
    _holding(db_session, acct, sec, quantity=10, cost_basis=350.0)
    _trade(db_session, acct, sec, price=38.0, on=date(2026, 9, 30))  # close outranks it
    db_session.commit()

    xef = _holdings(client)["XEF"]
    assert (xef["price"], xef["value"]) == (40.0, 400.0)
    assert xef["price_source"] == "close_price"
    assert xef["price_as_of"] == "2026-09-29"
    assert xef["gain"] == 50.0
    assert xef["gain_pct"] == 14.29


def test_falls_back_to_the_latest_trade_in_the_same_account(client, db_session):
    acct = make_account(db_session, plaid_account_id="tfsa", type="investment")
    other = make_account(db_session, plaid_account_id="rrsp", type="investment")
    sec = _security(db_session, "XIC")
    _holding(db_session, acct, sec, quantity=10)
    _trade(db_session, acct, sec, price=50.0, on=date(2026, 9, 1))
    _trade(db_session, acct, sec, price=55.0, on=date(2026, 9, 20), type="sell")
    # Neither of these is a trade price for this account's position.
    _trade(db_session, acct, sec, price=0.0, on=date(2026, 9, 25), type="cash", amount=-3.0)
    _trade(db_session, other, sec, price=99.0, on=date(2026, 9, 29))
    db_session.commit()

    xic = _holdings(client)["XIC"]
    assert (xic["price"], xic["value"]) == (55.0, 550.0)
    assert xic["price_source"] == "transaction"
    assert xic["price_as_of"] == "2026-09-20"


def test_a_price_in_another_currency_leaves_the_holding_unpriced(client, db_session):
    acct = make_account(db_session, type="investment")
    sec = _security(db_session, "VERGF", close_price=37.1, currency="USD")
    _holding(db_session, acct, sec, quantity=40.1272, cost_basis=1870.17, currency="CAD")
    _trade(db_session, acct, sec, price=50.7332, on=date(2026, 9, 28), currency="USD")
    db_session.commit()

    vergf = _holdings(client)["VERGF"]
    assert vergf["price"] is None
    assert vergf["value"] is None  # unknown, not a fake 0
    assert vergf["price_source"] is None
    assert vergf["gain"] is None
    assert vergf["cost_basis"] == 1870.17


def test_an_older_trade_in_the_holdings_currency_still_counts(client, db_session):
    acct = make_account(db_session, type="investment")
    sec = _security(db_session, "VERGF")
    _holding(db_session, acct, sec, quantity=10, currency="CAD")
    _trade(db_session, acct, sec, price=36.0, on=date(2026, 8, 1), currency="CAD")
    _trade(db_session, acct, sec, price=50.7332, on=date(2026, 9, 28), currency="USD")
    db_session.commit()

    vergf = _holdings(client)["VERGF"]
    assert vergf["price"] == 36.0
    assert vergf["price_as_of"] == "2026-08-01"


def test_an_unknown_currency_on_either_side_is_compatible(client, db_session):
    acct = make_account(db_session, type="investment")
    by_trade = _security(db_session, "XIC")
    by_close = _security(db_session, "VOO", close_price=500.0, currency="USD")
    _holding(db_session, acct, by_trade, quantity=2, currency="CAD")
    _holding(db_session, acct, by_close, quantity=1, currency=None)
    _trade(db_session, acct, by_trade, price=56.41, on=date(2026, 9, 30), currency=None)
    db_session.commit()

    holdings = _holdings(client)
    assert holdings["XIC"]["value"] == 112.82
    assert holdings["VOO"]["value"] == 500.0


# --------------------------------------------------------------------------- #
# the live Wealthsimple TFSA                                                   #
# --------------------------------------------------------------------------- #
def test_wealthsimple_tfsa_is_valued_at_its_account_balance(client, db_session):
    tfsa = _wealthsimple_tfsa(db_session)

    body = client.get("/api/investments/portfolio").json()

    assert body["total_value"] == 20960.59  # the balance, cash included
    assert body["cost_basis"] == 19294.47
    assert body["unrealized_gain"] == 1666.12
    assert body["unrealized_gain_pct"] == 8.64
    assert (body["holdings_count"], body["priced_count"], body["unpriced_count"]) == (4, 1, 3)
    assert body["by_account"] == [
        {"account_id": tfsa.id, "account_name": "TFSA", "value": 20960.59}
    ]
    # Only XIC can be priced, so weights fall back to what each holding cost.
    assert body["allocation_basis"] == "cost_basis"
    assert [(s["ticker"], s["amount"]) for s in body["allocation"]] == [
        ("VFVXF", 9603.68),
        ("XEF", 3921.37),
        ("XIC", 3899.25),
        ("VERGF", 1870.17),
    ]


def test_wealthsimple_seam_portfolio_and_goals_agree(client, db_session):
    _wealthsimple_tfsa(db_session)

    goal = client.post(
        "/api/finance/goals",
        json={"name": "Retirement", "target_amount": 500000.0, "target_date": "2060-01-01"},
    ).json()

    assert get_portfolio_value(db_session) == 20960.59
    assert client.get("/api/investments/portfolio").json()["total_value"] == 20960.59
    assert goal["current_value"] == 20960.59


def test_wealthsimple_holdings_show_unknown_rather_than_zero(client, db_session):
    _wealthsimple_tfsa(db_session)

    rows = client.get("/api/investments/holdings").json()

    # Priced first, then the unpriced ones by what they cost.
    assert [h["ticker"] for h in rows] == ["XIC", "VFVXF", "XEF", "VERGF"]
    xic = rows[0]
    assert xic["price"] == 56.41
    assert xic["value"] == 4058.73  # 71.9506 × 56.41
    assert xic["price_source"] == "transaction"
    assert xic["price_as_of"] == "2026-09-30"
    assert xic["gain"] == 159.48
    assert xic["gain_pct"] == 4.09
    for h in rows[1:]:
        assert (h["price"], h["value"], h["gain"], h["gain_pct"]) == (None, None, None, None)


# --------------------------------------------------------------------------- #
# gain and allocation                                                          #
# --------------------------------------------------------------------------- #
def test_allocation_uses_market_value_when_every_holding_is_priced(client, db_session):
    tfsa = make_account(db_session, plaid_account_id="tfsa", type="investment")
    rrsp = make_account(db_session, plaid_account_id="rrsp", type="investment")
    xic, xef = _security(db_session, "XIC"), _security(db_session, "XEF")
    _holding(db_session, tfsa, xic, quantity=10, cost_basis=100.0, price=60.0, value=600.0)
    _holding(db_session, rrsp, xic, quantity=5, cost_basis=50.0, price=60.0, value=300.0)
    _holding(db_session, rrsp, xef, quantity=10, cost_basis=900.0, price=40.0, value=400.0)
    db_session.commit()

    body = client.get("/api/investments/portfolio").json()

    assert body["allocation_basis"] == "market_value"
    # One slice per security, across accounts.
    assert [(s["ticker"], s["amount"]) for s in body["allocation"]] == [
        ("XIC", 900.0),
        ("XEF", 400.0),
    ]


def test_gain_leaves_out_investment_accounts_without_holdings(client, db_session):
    make_account(
        db_session, plaid_account_id="rrsp", type="investment", current_balance=10000.0
    )
    tfsa = make_account(
        db_session, plaid_account_id="tfsa", type="investment", current_balance=1100.0
    )
    _holding(db_session, tfsa, _security(db_session, "XIC"), quantity=10, cost_basis=1000.0)
    db_session.commit()

    body = client.get("/api/investments/portfolio").json()

    assert body["total_value"] == 11100.0
    # No cost to measure the RRSP's balance against; it isn't all "gain".
    assert body["unrealized_gain"] == 100.0
    assert body["unrealized_gain_pct"] == 10.0


def test_gain_is_unknown_when_a_holding_has_no_cost_basis(client, db_session):
    acct = make_account(db_session, type="investment", current_balance=1000.0)
    _holding(db_session, acct, _security(db_session, "XIC"), quantity=1, cost_basis=400.0)
    _holding(db_session, acct, _security(db_session, "XEF"), quantity=1, cost_basis=None)
    db_session.commit()

    body = client.get("/api/investments/portfolio").json()

    assert body["total_value"] == 1000.0
    assert body["cost_basis"] is None  # a partial sum would overstate the gain
    assert body["unrealized_gain"] is None
    assert body["unrealized_gain_pct"] is None


def test_gain_is_unknown_when_an_account_can_only_be_partly_valued(client, db_session):
    acct = make_account(db_session, type="investment")  # no balance from Plaid
    _holding(
        db_session, acct, _security(db_session, "XIC"), quantity=1, cost_basis=50.0, value=60.0
    )
    _holding(db_session, acct, _security(db_session, "XEF"), quantity=1, cost_basis=50.0)
    db_session.commit()

    body = client.get("/api/investments/portfolio").json()

    assert body["total_value"] == 60.0  # what could be priced
    assert body["unrealized_gain"] is None  # 60 - 100 would be a fake loss


def test_portfolio_is_empty_when_nothing_is_linked(client, db_session):
    make_account(db_session, type="depository", current_balance=500.0)
    db_session.commit()

    body = client.get("/api/investments/portfolio").json()

    assert body["total_value"] is None
    assert body["holdings_count"] == 0
    assert body["by_account"] == []
    assert body["allocation"] == []
    assert body["unrealized_gain"] is None
