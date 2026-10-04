"""Balance snapshotting: refresh live balances from Plaid, then persist one
point-in-time row per account per day. Used by the daily scheduler job and safe
to call ad hoc (idempotent per account/day)."""
from datetime import date

from plaid.model.accounts_get_request import AccountsGetRequest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Account, BalanceSnapshot, PlaidItem
from app.plaid_client import get_plaid_client


def apply_balances(db: Session, plaid_accounts) -> list[Account]:
    """Copy `balances.current` from Plaid account objects onto our rows; returns
    the rows updated.

    /accounts/get, /transactions/sync and /investments/holdings/get all return
    the item's accounts with Plaid's latest balances, so every sync path can keep
    balances current at no extra API cost. (Before this, only linking and the
    daily job updated them, so "Sync now" left an investment account's value —
    which is its balance — frozen until the next re-link.)
    """
    updated = []
    for acct in plaid_accounts or []:
        row = db.query(Account).filter_by(plaid_account_id=acct.account_id).first()
        if row is not None and acct.balances is not None:
            row.current_balance = acct.balances.current
            updated.append(row)
    return updated


def refresh_balances(db: Session) -> None:
    """Pull fresh current balances from Plaid for every linked account."""
    client = get_plaid_client()
    for item in db.query(PlaidItem).all():
        try:
            resp = client.accounts_get(AccountsGetRequest(access_token=item.access_token))
        except Exception:
            # A single failing item shouldn't abort the whole snapshot run.
            continue
        apply_balances(db, resp.accounts)


def write_snapshot(db: Session, account: Account, on: date | None = None) -> None:
    """Upsert `account`'s snapshot for `on` (default today) from its current balance.

    Only ever touches that one (account, day) row: earlier snapshots are history
    Plaid can't give back, so nothing here rewrites them.
    """
    on = on or date.today()
    existing = db.query(BalanceSnapshot).filter_by(account_id=account.id, date=on).first()
    if existing is None:
        db.add(BalanceSnapshot(account_id=account.id, date=on, balance=account.current_balance))
    else:
        existing.balance = account.current_balance  # keep the latest value for the day


def write_snapshots(db: Session, on: date | None = None) -> int:
    """Upsert one snapshot per account for `on` (default today). Returns rows written."""
    written = 0
    for account in db.query(Account).all():
        write_snapshot(db, account, on)
        written += 1
    return written


def run_daily_snapshot() -> None:
    """Scheduler entrypoint: owns its own session (jobs run outside a request)."""
    with SessionLocal() as db:
        refresh_balances(db)
        write_snapshots(db)
        db.commit()
