"""Plaid pipeline: create link token, exchange public token, sync transactions."""
from fastapi import APIRouter, Depends, HTTPException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy.orm import Session

from app.categorization import rule_category
from app.config import get_settings
from app.database import get_db
from app.models import Account, PlaidItem, Transaction
from app.plaid_client import get_plaid_client, normalize_category
from app.schemas import ExchangeTokenRequest, LinkTokenResponse, SyncResponse
from app.snapshots import write_snapshots

router = APIRouter(prefix="/api/plaid", tags=["plaid"])


@router.post("/create-link-token", response_model=LinkTokenResponse)
def create_link_token():
    settings = get_settings()
    client = get_plaid_client()
    request = LinkTokenCreateRequest(
        products=[Products(p) for p in settings.product_list],
        client_name="PKM Platform",
        country_codes=[CountryCode(c) for c in settings.country_code_list],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id="local-user"),
    )
    # Consent-only products (e.g. investments for Wealthsimple): captured if the
    # institution supports them, without filtering the institution list.
    consented = settings.additional_consented_product_list
    if consented:
        request.additional_consented_products = [Products(p) for p in consented]
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

    item = db.query(PlaidItem).filter_by(item_id=item_id).first()
    if item is None:
        item = PlaidItem(
            item_id=item_id,
            access_token=access_token,
            institution_name=payload.institution_name,
        )
        db.add(item)
        db.flush()  # assign item.id before creating accounts
    else:
        item.access_token = access_token

    # Pull accounts for this item and upsert them.
    accounts = client.accounts_get(AccountsGetRequest(access_token=access_token))
    for acct in accounts.accounts:
        existing = db.query(Account).filter_by(plaid_account_id=acct.account_id).first()
        balance = acct.balances.current if acct.balances else None
        currency = acct.balances.iso_currency_code if acct.balances else None
        if existing is None:
            db.add(
                Account(
                    plaid_item_id=item.id,
                    plaid_account_id=acct.account_id,
                    name=acct.name,
                    official_name=acct.official_name,
                    type=str(acct.type) if acct.type else None,
                    subtype=str(acct.subtype) if acct.subtype else None,
                    current_balance=balance,
                    currency=currency,
                )
            )
        else:
            existing.current_balance = balance

    db.commit()
    return {"item_id": item_id, "accounts_linked": len(accounts.accounts)}


@router.post("/sync", response_model=SyncResponse)
def sync_transactions(db: Session = Depends(get_db)):
    """Incrementally pull transactions for every linked item via /transactions/sync."""
    client = get_plaid_client()
    totals = {"added": 0, "modified": 0, "removed": 0}

    items = db.query(PlaidItem).all()
    if not items:
        raise HTTPException(status_code=400, detail="No linked institutions. Link one first.")

    for item in items:
        cursor = item.transactions_cursor
        has_more = True
        while has_more:
            request = TransactionsSyncRequest(access_token=item.access_token)
            if cursor:
                request.cursor = cursor
            try:
                resp = client.transactions_sync(request)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Plaid error: {exc}") from exc

            for txn in resp.added:
                _upsert_transaction(db, txn)
                totals["added"] += 1
            for txn in resp.modified:
                _upsert_transaction(db, txn)
                totals["modified"] += 1
            for removed in resp.removed:
                db.query(Transaction).filter_by(
                    plaid_transaction_id=removed.transaction_id
                ).delete()
                totals["removed"] += 1

            cursor = resp.next_cursor
            has_more = resp.has_more

        item.transactions_cursor = cursor
        db.commit()

    # Capture today's balances so net-worth history accrues on manual syncs too.
    write_snapshots(db)
    db.commit()

    return SyncResponse(**totals)


def _upsert_transaction(db: Session, txn) -> None:
    account = db.query(Account).filter_by(plaid_account_id=txn.account_id).first()
    if account is None:
        return  # transaction for an account we haven't stored; skip

    pfc = getattr(txn, "personal_finance_category", None)
    primary = pfc.primary if pfc else None
    merchant = getattr(txn, "merchant_name", None)

    # A user's merchant rule wins over Plaid's category so overrides survive sync.
    override = rule_category(db, merchant, txn.name)
    category = override or normalize_category(primary)

    existing = (
        db.query(Transaction)
        .filter_by(plaid_transaction_id=txn.transaction_id)
        .first()
    )
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
