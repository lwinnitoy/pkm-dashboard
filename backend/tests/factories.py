"""Small seeding helpers so tests read as data setup, not ORM boilerplate."""
from datetime import date

from sqlalchemy.orm import Session

from app.models import (
    Account,
    BalanceSnapshot,
    Holding,
    PlaidItem,
    Security,
    Transaction,
)

_txn_seq = 0
_holding_seq = 0


def make_item(db: Session, *, item_id: str = "item-1", name: str | None = "Bank") -> PlaidItem:
    item = PlaidItem(item_id=item_id, access_token="tok-" + item_id, institution_name=name)
    db.add(item)
    db.flush()
    return item


def make_account(
    db: Session,
    *,
    item: PlaidItem | None = None,
    plaid_account_id: str = "acct-1",
    name: str = "Checking",
    type: str = "depository",
    current_balance: float | None = None,
) -> Account:
    if item is None:
        item = make_item(db, item_id=f"item-for-{plaid_account_id}")
    acct = Account(
        plaid_item_id=item.id,
        plaid_account_id=plaid_account_id,
        name=name,
        type=type,
        current_balance=current_balance,
    )
    db.add(acct)
    db.flush()
    return acct


def make_transaction(
    db: Session,
    *,
    account: Account,
    amount: float,
    category: str | None = "Dining",
    txn_date: date | None = None,
    name: str = "Purchase",
    merchant_name: str | None = None,
) -> Transaction:
    global _txn_seq
    _txn_seq += 1
    txn = Transaction(
        account_id=account.id,
        plaid_transaction_id=f"txn-{_txn_seq}",
        date=txn_date or date.today(),
        name=name,
        merchant_name=merchant_name,
        amount=amount,
        category=category,
    )
    db.add(txn)
    db.flush()
    return txn


def make_security(db: Session, *, plaid_security_id: str = "sec-1", ticker: str = "VOO") -> Security:
    sec = Security(plaid_security_id=plaid_security_id, ticker_symbol=ticker, name=ticker)
    db.add(sec)
    db.flush()
    return sec


def make_holding(
    db: Session,
    *,
    account: Account,
    security: Security | None = None,
    institution_value: float | None = 100.0,
    quantity: float | None = 1.0,
) -> Holding:
    global _holding_seq
    _holding_seq += 1
    if security is None:
        security = make_security(db, plaid_security_id=f"sec-{_holding_seq}", ticker=f"T{_holding_seq}")
    holding = Holding(
        account_id=account.id,
        security_id=security.id,
        quantity=quantity,
        institution_value=institution_value,
    )
    db.add(holding)
    db.flush()
    return holding


def make_snapshot(db: Session, *, account: Account, on: date, balance: float | None) -> BalanceSnapshot:
    snap = BalanceSnapshot(account_id=account.id, date=on, balance=balance)
    db.add(snap)
    db.flush()
    return snap
