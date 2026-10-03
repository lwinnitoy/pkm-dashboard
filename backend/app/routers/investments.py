"""Investments module: sync holdings + investment transactions, and read endpoints.

Populated from Plaid's /investments/holdings/get and /investments/transactions/get
(e.g. for Wealthsimple). Sync is best-effort per item — items without investment
accounts are skipped rather than failing the whole run.
"""
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from plaid.exceptions import ApiException
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.investments_transactions_get_request import (
    InvestmentsTransactionsGetRequest,
)
from plaid.model.investments_transactions_get_request_options import (
    InvestmentsTransactionsGetRequestOptions,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.investments.valuation import HoldingValuation, value_portfolio
from app.models import Account, Holding, InvestmentTransaction, PlaidItem, Security
from app.plaid_client import get_plaid_client
from app.schemas import (
    AccountValue,
    AllocationSlice,
    HoldingOut,
    InvestmentsSyncResponse,
    InvestmentTransactionOut,
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
            # The as-of date reported for an institution price, so it has to move
            # on every sync, not just when the row is first created.
            updated_at=datetime.now(timezone.utc),
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


def _plaid_error(exc: ApiException) -> tuple[str, str]:
    """(error_code, message) from a Plaid ApiException, which carries a JSON body."""
    try:
        body = json.loads(exc.body or "{}")
    except (ValueError, TypeError):
        body = {}
    return (
        body.get("error_code") or "UNKNOWN",
        body.get("error_message") or str(exc).strip()[:200],
    )


def sync_all_investments(db: Session) -> dict:
    """Sync holdings + investment transactions for every item, best-effort (items
    without investment accounts are skipped, not errored). Shared by the endpoint,
    the manual sync flow, and the scheduled job.

    A skipped item reports *why*. "No holdings appeared" and "this item never
    consented to the investments product" look identical from the dashboard
    otherwise, and only one of them is fixable by re-linking.
    """
    client = get_plaid_client()
    totals = {"securities": 0, "holdings": 0, "investment_transactions": 0}
    synced = 0
    skipped: list[dict[str, str]] = []

    for item in db.query(PlaidItem).all():
        try:
            counts = sync_investments_for_item(db, client, item)
            db.commit()
            synced += 1
            for k in totals:
                totals[k] += counts[k]
        except ApiException as exc:
            # Usually "this item has no investment accounts" or "investments was
            # never consented for this item" — keep going, but say which.
            db.rollback()
            code, message = _plaid_error(exc)
            skipped.append(
                {
                    "institution": item.institution_name or f"item {item.item_id[:8]}",
                    "error_code": code,
                    "message": message,
                }
            )

    return {
        **totals,
        "items_synced": synced,
        "items_skipped": len(skipped),
        "skipped_details": skipped,
    }


@router.post("/sync", response_model=InvestmentsSyncResponse)
def sync_investments(db: Session = Depends(get_db)):
    return InvestmentsSyncResponse(**sync_all_investments(db))


def _rounded(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def _holding_order(h: HoldingValuation) -> tuple[bool, float]:
    """Priced holdings first, largest first; then unpriced ones by what they cost."""
    if h.value is not None:
        return (False, -h.value)
    return (True, -(h.cost_basis or 0.0))


@router.get("/holdings", response_model=list[HoldingOut])
def list_holdings(db: Session = Depends(get_db)):
    rows = [(a.account, h) for a in value_portfolio(db).accounts for h in a.holdings]
    rows.sort(key=lambda row: _holding_order(row[1]))
    return [
        HoldingOut(
            account_id=acct.id,
            account_name=acct.name,
            ticker=h.security.ticker_symbol,
            security_name=h.security.name,
            quantity=h.holding.quantity,
            price=h.price,
            value=_rounded(h.value),
            cost_basis=h.cost_basis,
            currency=h.holding.currency,
            price_source=h.price_source,
            price_as_of=h.price_as_of,
            gain=_rounded(h.gain),
            gain_pct=_rounded(h.gain_pct),
        )
        for acct, h in rows
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
    """Portfolio totals. `total_value` is the same figure the investments seam
    gives goals: both read it from `value_portfolio`, so they can't drift."""
    valuation = value_portfolio(db)
    holdings_count = len(valuation.holdings)
    by_account = sorted(
        valuation.accounts, key=lambda a: (a.value is None, -(a.value or 0.0))
    )
    return PortfolioSummary(
        total_value=_rounded(valuation.total_value),
        cost_basis=_rounded(valuation.cost_basis),
        unrealized_gain=_rounded(valuation.unrealized_gain),
        unrealized_gain_pct=_rounded(valuation.unrealized_gain_pct),
        holdings_count=holdings_count,
        priced_count=valuation.priced_count,
        unpriced_count=holdings_count - valuation.priced_count,
        by_account=[
            AccountValue(
                account_id=a.account.id, account_name=a.account.name, value=_rounded(a.value)
            )
            for a in by_account
        ],
        allocation_basis=valuation.allocation_basis,
        allocation=[
            AllocationSlice(
                ticker=sec.ticker_symbol, security_name=sec.name, amount=round(amount, 2)
            )
            for sec, amount in valuation.allocation()
        ],
    )
