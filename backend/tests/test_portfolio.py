"""app.investments.portfolio.get_portfolio_value."""
from app.investments.portfolio import get_portfolio_value

from tests.factories import make_account, make_holding


def test_none_when_no_holdings(db_session):
    assert get_portfolio_value(db_session) is None


def test_none_when_only_non_investment_accounts(db_session):
    make_account(db_session, type="depository", current_balance=1886.75)
    db_session.commit()

    assert get_portfolio_value(db_session) is None


def test_rounded_sum_with_holdings(db_session):
    # No balance on the account, so its priced holdings are the fallback.
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


def test_account_balance_wins_over_the_holdings_sum(db_session):
    """Plaid's balance for an investment account is the institution's total, so it
    also covers cash the holdings don't."""
    acct = make_account(db_session, type="investment", current_balance=20960.59)
    make_holding(db_session, account=acct, institution_value=0.0)  # Wealthsimple's 0s
    make_holding(db_session, account=acct, institution_value=4058.73)
    db_session.commit()

    assert get_portfolio_value(db_session) == 20960.59


def test_investment_account_without_holdings_counts(db_session):
    make_account(db_session, type="investment", current_balance=5000.0)
    db_session.commit()

    assert get_portfolio_value(db_session) == 5000.0


def test_sums_investment_accounts_and_any_account_holding_securities(db_session):
    make_account(db_session, plaid_account_id="a-cash", type="depository", current_balance=999.0)
    make_account(db_session, plaid_account_id="a-tfsa", type="investment", current_balance=100.0)
    other = make_account(db_session, plaid_account_id="a-other", type="other")
    make_holding(db_session, account=other, institution_value=50.0)
    db_session.commit()

    assert get_portfolio_value(db_session) == 150.0  # the chequing account isn't in it
