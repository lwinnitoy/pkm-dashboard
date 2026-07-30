"""Investments module: sync holdings + investment transactions, and read endpoints.

Populated from Plaid's /investments/holdings/get and /investments/transactions/get
(e.g. for Wealthsimple). Sync is best-effort per item — items without investment
accounts are skipped rather than failing the whole run.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from plaid.exceptions import ApiException
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.investments_transactions_get_request import (
    InvestmentsTransactionsGetRequest,
)
from plaid.model.investments_transactions_get_request_options import (
    InvestmentsTransactionsGetRequestOptions,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Holding, InvestmentTransaction, PlaidItem, Security
from app.plaid_client import get_plaid_client
from app.schemas import (
    AccountValue,
    HoldingOut,
    InvestmentsSyncResponse,
    InvestmentTransactionOut,
    PortfolioHolding,
    PortfolioSummary,
)

router = APIRouter(prefix="/api/investments", tags=["investments"])

_LOOKBACK_DAYS = 730  # Plaid serves up to 24 months of investment transactions
_PAGE = 500  # max page size for /investments/transactions/get


def _upsert_securities(db: Session, securities) -> dict[str, Security]:
    """Upsert Plaid securities; return a map of plaid_security_id -> Security row."""
    out: dict[str, Security] = {}
    for s in securities:
        row = db.query(Security).filter_by(plaid_security_id=s.security_id).first()
        values = dict(
            ticker_symbol=getattr(s, "ticker_symbol", None),
            name=getattr(s, "name", None),
            type=str(s.type) if getattr(s, "type", None) else None,
            close_price=getattr(s, "close_price", None),
            close_price_as_of=getattr(s, "close_price_as_of", None),
            currency=getattr(s, "iso_currency_code", None),
        )
        if row is None:
            row = Security(plaid_security_id=s.security_id, **values)
            db.add(row)
            db.flush()  # assign row.id for FK use
        else:
            for k, v in values.items():
                setattr(row, k, v)
        out[s.security_id] = row
    return out


def _account_map(db: Session, item: PlaidItem) -> dict[str, int]:
    """plaid_account_id -> local Account.id for this item's accounts."""
    return {
        a.plaid_account_id: a.id
        for a in db.query(Account).filter_by(plaid_item_id=item.id).all()
    }


def sync_investments_for_item(db: Session, client, item: PlaidItem) -> dict[str, int]:
    """Sync holdings + investment transactions for one item. Raises ApiException."""
    counts = {"securities": 0, "holdings": 0, "investment_transactions": 0}

    # --- Holdings (point-in-time) ---
    holdings_resp = client.investments_holdings_get(
        InvestmentsHoldingsGetRequest(access_token=item.access_token)
    )
    sec_map = _upsert_securities(db, holdings_resp.securities)
    counts["securities"] = len(sec_map)
    acct_map = _account_map(db, item)

    for h in holdings_resp.holdings:
        account_id = acct_map.get(h.account_id)
        security = sec_map.get(h.security_id)
        if account_id is None or security is None:
            continue
        existing = (
            db.query(Holding)
            .filter_by(account_id=account_id, security_id=security.id)
            .first()
        )
        values = dict(
            quantity=h.quantity,
            institution_price=getattr(h, "institution_price", None),
            institution_value=getattr(h, "institution_value", None),
            cost_basis=getattr(h, "cost_basis", None),
            currency=getattr(h, "iso_currency_code", None),
        )
        if existing is None:
            db.add(Holding(account_id=account_id, security_id=security.id, **values))
        else:
            for k, v in values.items():
                setattr(existing, k, v)
        counts["holdings"] += 1

    # --- Investment transactions (paginated over the lookback window) ---
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    offset = 0
    total = None
    while total is None or offset < total:
        resp = client.investments_transactions_get(
            InvestmentsTransactionsGetRequest(
                access_token=item.access_token,
                start_date=start,
                end_date=end,
                options=InvestmentsTransactionsGetRequestOptions(
                    count=_PAGE, offset=offset
                ),
            )
        )
        total = resp.total_investment_transactions
        # Later pages may reference securities not seen in holdings.
        sec_map.update(_upsert_securities(db, resp.securities))

        batch = resp.investment_transactions
        if not batch:
            break
        for it in batch:
            account_id = acct_map.get(it.account_id)
            if account_id is None:
                continue
            security = sec_map.get(getattr(it, "security_id", None))
            existing = (
                db.query(InvestmentTransaction)
                .filter_by(plaid_investment_transaction_id=it.investment_transaction_id)
                .first()
            )
            values = dict(
                account_id=account_id,
                security_id=security.id if security else None,
                date=it.date,
                name=getattr(it, "name", None),
                quantity=getattr(it, "quantity", None),
                amount=getattr(it, "amount", None),
                price=getattr(it, "price", None),
                fees=getattr(it, "fees", None),
                type=str(it.type) if getattr(it, "type", None) else None,
                subtype=str(it.subtype) if getattr(it, "subtype", None) else None,
                currency=getattr(it, "iso_currency_code", None),
            )
            if existing is None:
                db.add(
                    InvestmentTransaction(
                        plaid_investment_transaction_id=it.investment_transaction_id,
                        **values,
                    )
                )
            else:
                for k, v in values.items():
                    setattr(existing, k, v)
            counts["investment_transactions"] += 1

        offset += len(batch)

    return counts


@router.post("/sync", response_model=InvestmentsSyncResponse)
def sync_investments(db: Session = Depends(get_db)):
    client = get_plaid_client()
    totals = {"securities": 0, "holdings": 0, "investment_transactions": 0}
    synced = skipped = 0

    for item in db.query(PlaidItem).all():
        try:
            counts = sync_investments_for_item(db, client, item)
            db.commit()
            synced += 1
            for k in totals:
                totals[k] += counts[k]
        except ApiException:
            # Item has no investment accounts / product not supported — skip it.
            db.rollback()
            skipped += 1

    return InvestmentsSyncResponse(
        securities=totals["securities"],
        holdings=totals["holdings"],
        investment_transactions=totals["investment_transactions"],
        items_synced=synced,
        items_skipped=skipped,
    )


@router.get("/holdings", response_model=list[HoldingOut])
def list_holdings(db: Session = Depends(get_db)):
    rows = (
        db.query(Holding, Account, Security)
        .join(Account, Holding.account_id == Account.id)
        .join(Security, Holding.security_id == Security.id)
        .order_by(Holding.institution_value.desc().nullslast())
        .all()
    )
    return [
        HoldingOut(
            account_id=acct.id,
            account_name=acct.name,
            ticker=sec.ticker_symbol,
            security_name=sec.name,
            quantity=h.quantity,
            price=h.institution_price,
            value=h.institution_value,
            cost_basis=h.cost_basis,
            currency=h.currency,
        )
        for h, acct, sec in rows
    ]


@router.get("/transactions", response_model=list[InvestmentTransactionOut])
def list_investment_transactions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(InvestmentTransaction, Security)
        .outerjoin(Security, InvestmentTransaction.security_id == Security.id)
        .order_by(
            InvestmentTransaction.date.desc(), InvestmentTransaction.id.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        InvestmentTransactionOut(
            id=it.id,
            date=it.date,
            name=it.name,
            ticker=sec.ticker_symbol if sec else None,
            type=it.type,
            subtype=it.subtype,
            quantity=it.quantity,
            price=it.price,
            amount=it.amount,
            fees=it.fees,
            currency=it.currency,
        )
        for it, sec in rows
    ]


@router.get("/portfolio", response_model=PortfolioSummary)
def portfolio_summary(db: Session = Depends(get_db)):
    total = db.query(
        func.coalesce(func.sum(Holding.institution_value), 0.0)
    ).scalar()

    by_account_rows = (
        db.query(
            Account.id,
            Account.name,
            func.coalesce(func.sum(Holding.institution_value), 0.0),
        )
        .join(Holding, Holding.account_id == Account.id)
        .group_by(Account.id, Account.name)
        .order_by(func.sum(Holding.institution_value).desc())
        .all()
    )

    top_rows = (
        db.query(
            Security.ticker_symbol,
            Security.name,
            func.coalesce(func.sum(Holding.institution_value), 0.0),
        )
        .join(Holding, Holding.security_id == Security.id)
        .group_by(Security.id, Security.ticker_symbol, Security.name)
        .order_by(func.sum(Holding.institution_value).desc())
        .limit(10)
        .all()
    )

    return PortfolioSummary(
        total_value=round(total, 2),
        holdings_count=db.query(func.count(Holding.id)).scalar(),
        by_account=[
            AccountValue(account_id=aid, account_name=name, value=round(val, 2))
            for aid, name, val in by_account_rows
        ],
        top_holdings=[
            PortfolioHolding(ticker=tk, security_name=nm, value=round(val, 2))
            for tk, nm, val in top_rows
        ],
    )
