"""Dashboard read endpoints: transactions, spending summary, accounts."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Transaction
from app.schemas import (
    AccountOut,
    CategorySpend,
    SummaryResponse,
    TransactionOut,
)

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    category: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc())
    if category:
        query = query.filter(Transaction.category == category)
    return query.offset(offset).limit(limit).all()


@router.get("/summary", response_model=SummaryResponse)
def spending_summary(
    period: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    db: Session = Depends(get_db),
):
    since = date.today() - timedelta(days=period)

    # Spending only: Plaid uses positive amounts for money leaving the account,
    # and we exclude Income/Transfers from "spent".
    spend_filter = (
        Transaction.date >= since,
        Transaction.amount > 0,
        Transaction.category.notin_(["Income", "Transfers"]),
    )

    total = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(*spend_filter).scalar()
    count = db.query(func.count(Transaction.id)).filter(*spend_filter).scalar()

    rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .filter(*spend_filter)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    by_category = [
        CategorySpend(category=cat or "Uncategorized", total=round(tot, 2), count=cnt)
        for cat, tot, cnt in rows
    ]

    return SummaryResponse(
        period_days=period,
        total_spent=round(total, 2),
        transaction_count=count,
        by_category=by_category,
    )


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).all()
