"""app.investments.portfolio.get_portfolio_value."""
from app.investments.portfolio import get_portfolio_value

from tests.factories import make_account, make_holding


def test_none_when_no_holdings(db_session):
    assert get_portfolio_value(db_session) is None


def test_rounded_sum_with_holdings(db_session):
    acct = make_account(db_session, type="investment")
    make_holding(db_session, account=acct, institution_value=1000.555)
    make_holding(db_session, account=acct, institution_value=250.111)
    db_session.commit()

    # 1000.555 + 250.111 = 1250.666 -> rounded to 1250.67
    assert get_portfolio_value(db_session) == 1250.67


def test_zero_value_holdings_still_not_none(db_session):
    """A holding with a null/zero value still means investments are 'linked'."""
    acct = make_account(db_session, type="investment")
    make_holding(db_session, account=acct, institution_value=None)
    db_session.commit()

    assert get_portfolio_value(db_session) == 0.0
