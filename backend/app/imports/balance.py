"""Balances for manual (imported) accounts.

A statement export has no balance column, so a manual account can't learn its
balance the way a Plaid account does. Instead the owner enters one, read off the
bank's app, as of a date: the *anchor*. Every transaction dated after the anchor
moves the balance; anything on or before it is already reflected in the number
they typed, which is why back-filling older statements leaves it alone.

The derived value is stored in `current_balance`, so the accounts list, the daily
snapshot and net worth read manual and Plaid accounts the same way.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Account, Transaction
from app.routers.finance import LIABILITY_TYPES
from app.snapshots import write_snapshot


def roll_forward(db: Session, account: Account) -> None:
    """Recompute `current_balance` from the anchor. No-op without one.

    Amounts follow Plaid's sign (positive = money out), so a purchase lowers an
    asset account's balance but raises a credit card's, whose balance is the
    amount owed.
    """
    if account.balance_anchor is None or account.balance_anchor_date is None:
        return
    moved = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(
            Transaction.account_id == account.id,
            Transaction.date > account.balance_anchor_date,
        )
        .scalar()
    )
    sign = 1 if (account.type or "").lower() in LIABILITY_TYPES else -1
    account.current_balance = round(account.balance_anchor + sign * float(moved), 2)


def refresh(db: Session, account: Account) -> None:
    """Re-derive an anchored account's balance after its transactions or its type
    changed, and refresh today's snapshot so net worth reflects it now rather
    than at the next daily run. No-op without an anchor."""
    if account.balance_anchor is None:
        return
    roll_forward(db, account)
    write_snapshot(db, account)


def set_anchor(db: Session, account: Account, balance: float | None, as_of: date) -> None:
    """Record the owner's balance as of `as_of`; None clears it."""
    account.balance_anchor = balance
    account.balance_anchor_date = as_of if balance is not None else None
    if balance is None:
        account.current_balance = None
        write_snapshot(db, account)
        return
    refresh(db, account)
