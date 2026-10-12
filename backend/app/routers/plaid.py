"""Plaid pipeline: create link token, exchange public token, sync transactions."""
import logging
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException
from plaid.exceptions import ApiException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorization import rule_category
from app.config import get_settings
from app.database import get_db
from app.models import SOURCE_PLAID, Account, PlaidItem, Transaction
from app.plaid_client import (
    get_plaid_client,
    item_label,
    normalize_category,
    plaid_error,
    remove_item,
    skipped_item,
)
from app.schemas import ExchangeTokenRequest, LinkTokenResponse, SyncResponse
from app.snapshots import apply_balances, write_snapshots

router = APIRouter(prefix="/api/plaid", tags=["plaid"])
logger = logging.getLogger(__name__)


@router.post("/create-link-token", response_model=LinkTokenResponse)
def create_link_token():
    settings = get_settings()
    client = get_plaid_client()
    request = LinkTokenCreateRequest(
        products=[Products(p) for p in settings.product_list],
        client_name="Ledger",
        country_codes=[CountryCode(c) for c in settings.country_code_list],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id="local-user"),
    )
    # Consent-only products (e.g. investments for Wealthsimple): captured if the
    # institution supports them, without filtering the institution list.
    consented = settings.additional_consented_product_list
    if consented:
        request.additional_consented_products = [Products(p) for p in consented]
    # Required for OAuth institutions (e.g. RBC). Must exactly match a redirect URI
    # registered in the Plaid dashboard.
    if settings.plaid_redirect_uri:
        request.redirect_uri = settings.plaid_redirect_uri
    try:
        response = client.link_token_create(request)
    except Exception as exc:  # surface Plaid errors to the client for debugging
        raise HTTPException(status_code=502, detail=f"Plaid error: {exc}") from exc
    return LinkTokenResponse(link_token=response.link_token)


@router.post("/exchange-token")
def exchange_token(payload: ExchangeTokenRequest, db: Session = Depends(get_db)):
    client = get_plaid_client()
    try:
        exchange = client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=payload.public_token)
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plaid error: {exc}") from exc

    access_token = exchange.access_token
    item_id = exchange.item_id

    item = _item_for_relink(db, item_id, payload.institution_id)
    replaced_token = None
    if item is None:
        item = PlaidItem(
            item_id=item_id,
            access_token=access_token,
            institution_id=payload.institution_id,
            institution_name=payload.institution_name,
        )
        db.add(item)
        db.flush()  # assign item.id before creating accounts
    else:
        # Re-link of a bank we already have: adopt the new credentials onto the
        # existing row rather than letting a second copy of every account appear.
        if item.item_id != item_id:
            # A new Plaid Item: its transaction ids are all new too, so the re-walk
            # below would re-add every transaction we already hold. Detach them so
            # sync can adopt each one instead (see _adopt_detached).
            _detach_transactions(db, item)
            replaced_token = item.access_token
        item.item_id = item_id
        item.access_token = access_token
        item.institution_id = payload.institution_id or item.institution_id
        item.institution_name = payload.institution_name or item.institution_name
        item.transactions_cursor = None  # ids changed; re-walk from the start

    accounts = client.accounts_get(AccountsGetRequest(access_token=access_token))
    for acct in accounts.accounts:
        _upsert_account(db, item, acct)

    db.commit()
    if replaced_token:
        # Only once the new Item is safely stored: the old one is now unreachable
        # from the app but still live (and billed) at Plaid until removed.
        remove_item(client, replaced_token)
    return {"item_id": item_id, "accounts_linked": len(accounts.accounts)}


def _detach_transactions(db: Session, item: PlaidItem) -> None:
    """Prepare an item's transactions for the re-walk after a re-link.

    Pending rows are dropped: Plaid re-sends them, possibly already posted under a
    different date, so matching them up would be guesswork. Posted rows keep their
    data but lose their (now dead) Plaid id, which makes them adoptable by the
    matching transaction from the new Item. Rows older than the new Item's history
    window are never adopted and simply stay as history.
    """
    account_ids = select(Account.id).where(Account.plaid_item_id == item.id)
    plaid_rows = db.query(Transaction).filter(
        Transaction.account_id.in_(account_ids),
        Transaction.source == SOURCE_PLAID,
    )
    plaid_rows.filter(Transaction.pending.is_(True)).delete(synchronize_session=False)
    plaid_rows.update({Transaction.plaid_transaction_id: None}, synchronize_session=False)


def _item_for_relink(db: Session, item_id: str, institution_id: str | None) -> PlaidItem | None:
    """The existing row this link should update, if any.

    Plaid mints a fresh `item_id` (and fresh `account_id`s) every time you go
    through Link, so matching on `item_id` alone never recognizes a re-link and
    every reconnect silently duplicates the institution's accounts. The
    institution is the stable identity.
    """
    existing = db.query(PlaidItem).filter_by(item_id=item_id).first()
    if existing is not None:
        return existing
    if institution_id:
        return db.query(PlaidItem).filter_by(institution_id=institution_id).first()
    return None


def _upsert_account(db: Session, item: PlaidItem, acct) -> None:
    """Attach one Plaid account to `item`, reusing the existing row where possible.

    Matched by `plaid_account_id` first, then by mask + name among this item's
    accounts — the fallback that carries transaction history across a re-link,
    since the Plaid id will have changed. Deliberately requires a mask match: a
    wrong guess would graft one account's history onto another.
    """
    balance = acct.balances.current if acct.balances else None
    currency = acct.balances.iso_currency_code if acct.balances else None
    mask = getattr(acct, "mask", None)

    existing = db.query(Account).filter_by(plaid_account_id=acct.account_id).first()
    if existing is None and mask:
        existing = (
            db.query(Account)
            .filter_by(plaid_item_id=item.id, mask=mask, name=acct.name)
            .first()
        )
        if existing is not None:
            existing.plaid_account_id = acct.account_id  # rebind to the new id

    if existing is None:
        db.add(
            Account(
                plaid_item_id=item.id,
                plaid_account_id=acct.account_id,
                name=acct.name,
                mask=mask,
                official_name=acct.official_name,
                type=str(acct.type) if acct.type else None,
                subtype=str(acct.subtype) if acct.subtype else None,
                current_balance=balance,
                currency=currency,
            )
        )
        return

    existing.plaid_item_id = item.id
    existing.mask = mask or existing.mask
    existing.current_balance = balance
    existing.currency = currency or existing.currency


# Plaid's documented retry for a cursor walk that raced a data update.
_MUTATION_DURING_PAGINATION = "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"
_MAX_SYNC_ATTEMPTS = 3


@dataclass
class _SyncBatch:
    """Every page since an item's saved cursor, gathered before anything is applied."""

    added: list = field(default_factory=list)
    modified: list = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    accounts: list | None = None
    next_cursor: str | None = None


def _fetch_item_changes(client, item: PlaidItem) -> _SyncBatch:
    """Walk /transactions/sync from the item's cursor to the end.

    Pages are collected first and applied afterwards, as Plaid recommends: if the
    walk fails part-way, nothing has been written and the saved cursor still
    points at the start, so the next sync simply retries. A mutation during
    pagination restarts the walk from that saved cursor.
    """
    for attempt in range(1, _MAX_SYNC_ATTEMPTS + 1):
        batch = _SyncBatch()
        cursor = item.transactions_cursor
        try:
            while True:
                request = TransactionsSyncRequest(access_token=item.access_token)
                if cursor:
                    request.cursor = cursor
                resp = client.transactions_sync(request)
                batch.added.extend(resp.added)
                batch.modified.extend(resp.modified)
                batch.removed.extend(r.transaction_id for r in resp.removed)
                batch.accounts = getattr(resp, "accounts", None) or batch.accounts
                cursor = resp.next_cursor
                if not resp.has_more:
                    batch.next_cursor = cursor
                    return batch
        except ApiException as exc:
            code, _ = plaid_error(exc)
            if code != _MUTATION_DURING_PAGINATION or attempt == _MAX_SYNC_ATTEMPTS:
                raise
            logger.info("%s changed mid-sync; restarting (attempt %d)", item_label(item), attempt)
    raise AssertionError("unreachable")


def _apply_item_changes(db: Session, batch: _SyncBatch) -> None:
    apply_balances(db, batch.accounts)
    # Accounts whose rows were detached by a re-link; only these can adopt.
    adoptable = {
        account_id
        for (account_id,) in db.query(Transaction.account_id)
        .filter(Transaction.source == SOURCE_PLAID, Transaction.plaid_transaction_id.is_(None))
        .distinct()
    }
    for txn in batch.added:
        _upsert_transaction(db, txn, adoptable)
    # The session doesn't autoflush, and a later page may modify or remove a row
    # an earlier page added.
    db.flush()
    for txn in batch.modified:
        _upsert_transaction(db, txn, adoptable)
    db.flush()
    if batch.removed:
        db.query(Transaction).filter(
            Transaction.plaid_transaction_id.in_(batch.removed)
        ).delete(synchronize_session=False)


def sync_all_items(db: Session) -> dict:
    """Incrementally pull transactions for every linked item via /transactions/sync,
    then snapshot balances. Shared by the manual endpoint and the scheduled job;
    a no-op (zero totals) when nothing is linked.

    Each item is synced on its own: one bank needing a re-login (ITEM_LOGIN_REQUIRED)
    is reported in `skipped_details` rather than stopping every other bank, and the
    day's balance snapshot is still written.
    """
    client = get_plaid_client()
    totals = {"added": 0, "modified": 0, "removed": 0}
    skipped: list[dict[str, str]] = []

    for item in db.query(PlaidItem).all():
        try:
            batch = _fetch_item_changes(client, item)
        except Exception as exc:
            entry = skipped_item(item, exc)
            logger.warning("transaction sync skipped %s: %s", entry["institution"], entry["error_code"])
            skipped.append(entry)
            continue

        _apply_item_changes(db, batch)
        item.transactions_cursor = batch.next_cursor
        db.commit()
        totals["added"] += len(batch.added)
        totals["modified"] += len(batch.modified)
        totals["removed"] += len(batch.removed)

    # Capture today's balances (refreshed above) so net-worth history accrues on
    # every sync.
    write_snapshots(db)
    db.commit()

    return {**totals, "items_skipped": len(skipped), "skipped_details": skipped}


@router.post("/sync", response_model=SyncResponse)
def sync_transactions(db: Session = Depends(get_db)):
    """Manual sync trigger. Errors if nothing is linked so the UI can prompt to link."""
    if db.query(PlaidItem).first() is None:
        raise HTTPException(status_code=400, detail="No linked institutions. Link one first.")
    return SyncResponse(**sync_all_items(db))


def _adopt_detached(db: Session, account_id: int, txn) -> Transaction | None:
    """The row a re-link detached that this incoming transaction is a copy of.

    Same account, date and amount; among several (two identical coffees), prefer
    the same description, and each row can be adopted only once because adopting
    gives it an id.
    """
    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == account_id,
            Transaction.source == SOURCE_PLAID,
            Transaction.plaid_transaction_id.is_(None),
            Transaction.date == txn.date,
            Transaction.amount == txn.amount,
        )
        .order_by(Transaction.id)
        .all()
    )
    if not candidates:
        return None
    return next((c for c in candidates if c.name == txn.name), candidates[0])


def _upsert_transaction(db: Session, txn, adoptable: set[int] = frozenset()) -> None:
    account = db.query(Account).filter_by(plaid_account_id=txn.account_id).first()
    if account is None:
        return  # transaction for an account we haven't stored; skip

    pfc = getattr(txn, "personal_finance_category", None)
    primary = pfc.primary if pfc else None
    detailed = getattr(pfc, "detailed", None) if pfc else None
    merchant = getattr(txn, "merchant_name", None)

    # A user's merchant rule wins over Plaid's category so overrides survive sync.
    override = rule_category(db, merchant, txn.name)
    category = override or normalize_category(primary, detailed)

    existing = (
        db.query(Transaction)
        .filter_by(plaid_transaction_id=txn.transaction_id)
        .first()
    )
    adopted = False
    if existing is None and account.id in adoptable:
        existing = _adopt_detached(db, account.id, txn)
        adopted = existing is not None
    values = dict(
        account_id=account.id,
        date=txn.date,
        name=txn.name,
        merchant_name=merchant,
        amount=txn.amount,
        currency=txn.iso_currency_code,
        category=category,
        plaid_category=primary,
        pending=bool(txn.pending),
    )
    if existing is None:
        db.add(Transaction(plaid_transaction_id=txn.transaction_id, **values))
    else:
        for key, val in values.items():
            setattr(existing, key, val)
        if adopted:
            existing.plaid_transaction_id = txn.transaction_id
            db.flush()  # so the next identical transaction can't adopt it too
