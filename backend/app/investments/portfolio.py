"""Investments integration seam.

This module is the ONLY surface the finance/goals code depends on for investment
data (see docs/investments-contract.md). Its total is the same number the
investments router's /portfolio endpoint reports as `total_value`: both come
from `value_portfolio`, so the two can't drift apart.
"""
from sqlalchemy.orm import Session

from app.investments.valuation import value_portfolio


def get_portfolio_value(db: Session) -> float | None:
    """Total current value across all investment accounts.

    Each account counts at its institution-reported balance (uninvested cash
    included), or at the sum of its priced holdings when it has no balance.
    Returns None when no investments are linked (no investment accounts and no
    holdings), so callers can show a "connect investments" empty state rather
    than a misleading $0 line.
    """
    total = value_portfolio(db).total_value
    return None if total is None else round(total, 2)
