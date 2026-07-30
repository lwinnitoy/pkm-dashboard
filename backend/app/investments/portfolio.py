"""Investments integration seam.

This module is the ONLY surface the finance/goals code depends on for investment
data (see docs/investments-contract.md). It mirrors the total computed by the
investments router's /portfolio endpoint (sum of holdings' institution_value).
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Holding


def get_portfolio_value(db: Session) -> float | None:
    """Total current market value across all investment holdings.

    Returns None when no holdings are linked yet, so callers can show a
    "connect investments" empty state rather than a misleading $0 line.
    """
    if db.query(Holding.id).first() is None:
        return None
    total = db.query(func.coalesce(func.sum(Holding.institution_value), 0.0)).scalar()
    return round(float(total), 2)
