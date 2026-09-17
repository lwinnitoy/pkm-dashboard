"""Monthly category budgets: CRUD plus a per-month status view (spent vs limit)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Budget, Transaction
from app.routers.finance import IS_SPEND_CATEGORY
from app.schemas import BudgetCreate, BudgetOut, BudgetStatus, BudgetStatusItem, BudgetUpdate

router = APIRouter(prefix="/api/finance/budgets", tags=["budgets"])


def _month_bounds(month: str) -> tuple[date, date]:
    """[start, end) date range for a 'YYYY-MM' string."""
    try:
        year, mon = (int(p) for p in month.split("-"))
        start = date(year, mon, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="month must be 'YYYY-MM'") from exc
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


@router.get("", response_model=list[BudgetOut])
def list_budgets(db: Session = Depends(get_db)):
    return db.query(Budget).order_by(Budget.category).all()


@router.post("", response_model=BudgetOut)
def upsert_budget(payload: BudgetCreate, db: Session = Depends(get_db)):
    """Create or update the budget for a category (idempotent by category)."""
    budget = db.query(Budget).filter_by(category=payload.category).first()
    if budget is None:
        budget = Budget(category=payload.category, monthly_limit=payload.monthly_limit)
        db.add(budget)
    else:
        budget.monthly_limit = payload.monthly_limit
    db.commit()
    db.refresh(budget)
    return budget


@router.patch("/{budget_id}", response_model=BudgetOut)
def update_budget(budget_id: int, payload: BudgetUpdate, db: Session = Depends(get_db)):
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    for key, val in payload.model_dump(exclude_unset=True).items():
        setattr(budget, key, val)
    db.commit()
    db.refresh(budget)
    return budget


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()


@router.get("/status", response_model=BudgetStatus)
def budget_status(
    month: str | None = Query(None, description="YYYY-MM; defaults to current month"),
    db: Session = Depends(get_db),
):
    """Per-category spent vs limit for a calendar month. Includes categories with
    spending but no budget set (limit=None) so they can be surfaced for budgeting."""
    month = month or date.today().strftime("%Y-%m")
    start, end = _month_bounds(month)

    rows = (
        db.query(Transaction.category, func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.amount > 0,
            IS_SPEND_CATEGORY,
        )
        .group_by(Transaction.category)
        .all()
    )
    spent_by_cat = {(cat or "Uncategorized"): round(float(tot), 2) for cat, tot in rows}

    budgets = db.query(Budget).all()
    items: list[BudgetStatusItem] = []

    for b in budgets:
        spent = spent_by_cat.get(b.category, 0.0)
        pct = round(spent / b.monthly_limit * 100, 1) if b.monthly_limit > 0 else None
        items.append(
            BudgetStatusItem(
                budget_id=b.id,
                category=b.category,
                limit=round(b.monthly_limit, 2),
                spent=spent,
                remaining=round(b.monthly_limit - spent, 2),
                pct=pct,
            )
        )

    budgeted = {b.category for b in budgets}
    for cat, spent in spent_by_cat.items():
        if cat not in budgeted:
            items.append(
                BudgetStatusItem(
                    budget_id=None, category=cat, limit=None, spent=spent,
                    remaining=None, pct=None,
                )
            )

    # Budgeted first (most-consumed at top), then unbudgeted by spend.
    items.sort(key=lambda i: (i.limit is None, -(i.pct or 0), -i.spent))

    return BudgetStatus(
        month=month,
        total_limit=round(sum(b.monthly_limit for b in budgets), 2),
        total_spent=round(sum(spent_by_cat.values()), 2),
        items=items,
    )
