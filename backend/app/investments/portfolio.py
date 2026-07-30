"""Investments integration seam.

This module is the ONLY surface the finance/goals code depends on for investment
data. The Wealthsimple worktree owns the real implementation and replaces the stub
below at this same path & signature. See docs/investments-contract.md.

Until that branch merges, get_portfolio_value returns None and dependent features
(retirement-goal projection, net-worth-with-investments) degrade gracefully.
"""
from sqlalchemy.orm import Session


def get_portfolio_value(db: Session) -> float | None:
    """Total current market value across all investment holdings.

    Returns None when no investment source is linked yet (stub behavior), so
    callers can show a "connect investments" empty state rather than a $0 line.
    """
    return None
