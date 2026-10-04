"""How much goes into the investment accounts each month, worked out from Plaid's
investment transactions. The Goals page's "current direction" projects forward
from it.

Only cash moving in or out counts: a contribution/deposit adds, a withdrawal
subtracts. Buys, sells, dividends and reinvestments move money *within* the
account, so they're growth, not saving.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import InvestmentTransaction

_FLOW_TYPES = ("cash", "transfer")
CONTRIBUTION_SUBTYPES = ("contribution", "deposit")
WITHDRAWAL_SUBTYPES = ("withdrawal",)

LOOKBACK_DAYS = 365
# Plaid often returns only recent history for a fresh link (a week, for the
# owner's Wealthsimple). Averaging a week into a "monthly" figure is noise, so
# below this the rate is unknown and the UI asks instead.
MIN_HISTORY_DAYS = 60
_DAYS_PER_MONTH = 365.25 / 12


@dataclass
class ContributionRate:
    monthly: float | None  # None until there's MIN_HISTORY_DAYS of history
    net_total: float  # contributions minus withdrawals over the window
    count: int  # contribution + withdrawal transactions seen
    history_days: int  # span the average covers (0 = no history at all)


def contribution_rate(
    db: Session, account_ids: list[int], today: date | None = None
) -> ContributionRate:
    today = today or date.today()
    if not account_ids:
        return ContributionRate(None, 0.0, 0, 0)
    rows = (
        db.query(InvestmentTransaction)
        .filter(
            InvestmentTransaction.account_id.in_(account_ids),
            InvestmentTransaction.date >= today - timedelta(days=LOOKBACK_DAYS),
        )
        .all()
    )
    if not rows:
        return ContributionRate(None, 0.0, 0, 0)

    # The window starts at the oldest transaction Plaid gave us at all, not the
    # oldest contribution: three months of history with one deposit is a slow
    # month-rate, not a fast one.
    history_days = (today - min(r.date for r in rows)).days + 1
    net, count = 0.0, 0
    for r in rows:
        if (r.type or "").lower() not in _FLOW_TYPES or r.amount is None:
            continue
        subtype = (r.subtype or "").lower()
        # Plaid's sign convention for cash moving into the account isn't
        # consistent across institutions, so the subtype decides the direction.
        if subtype in CONTRIBUTION_SUBTYPES:
            net += abs(r.amount)
            count += 1
        elif subtype in WITHDRAWAL_SUBTYPES:
            net -= abs(r.amount)
            count += 1

    monthly = (
        round(net / (history_days / _DAYS_PER_MONTH), 2)
        if history_days >= MIN_HISTORY_DAYS
        else None
    )
    return ContributionRate(monthly, round(net, 2), count, history_days)
