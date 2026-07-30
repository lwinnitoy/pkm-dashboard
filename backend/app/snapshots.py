"""Balance snapshotting: refresh live balances from Plaid, then persist one
point-in-time row per account per day. Used by the daily scheduler job and safe
to call ad hoc (idempotent per account/day)."""
from datetime import date

from plaid.model.accounts_get_request import AccountsGetRequest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Account, BalanceSnapshot, PlaidItem
from app.plaid_client import get_plaid_client


def refresh_balances(db: Session) -> None:
    """Pull fresh current balances from Plaid for every linked account."""
    client = get_plaid_client()
    for item in db.query(PlaidItem).all():
        try:
            resp = client.accounts_get(AccountsGetRequest(access_token=item.access_token))
        except Exception:
            # A single failing item shouldn't abort the whole snapshot run.
            continue
        for acct in resp.accounts:
            row = db.query(Account).filter_by(plaid_account_id=acct.account_id).first()
            if row is not None and acct.balances is not None:
                row.current_balance = acct.balances.current


def write_snapshots(db: Session, on: date | None = None) -> int:
    """Upsert one snapshot per account for `on` (default today). Returns rows written."""
    on = on or date.today()
    written = 0
    for account in db.query(Account).all():
        existing = (
            db.query(BalanceSnapshot)
            .filter_by(account_id=account.id, date=on)
            .first()
        )
        if existing is None:
            db.add(
                BalanceSnapshot(account_id=account.id, date=on, balance=account.current_balance)
            )
        else:
            existing.balance = account.current_balance  # keep the latest value for the day
        written += 1
    return written


def run_daily_snapshot() -> None:
    """Scheduler entrypoint: owns its own session (jobs run outside a request)."""
    with SessionLocal() as db:
        refresh_balances(db)
        write_snapshots(db)
        db.commit()
