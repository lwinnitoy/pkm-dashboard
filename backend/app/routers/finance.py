"""Dashboard read endpoints: transactions, spending summary, accounts,
spending trend, top merchants, category comparison, net worth, and goals."""
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.categorization import match_key, upsert_rule_and_apply
from app.database import get_db
from app.investments.portfolio import get_portfolio_value
from app.models import Account, BalanceSnapshot, Category, Goal, Transaction
from app.schemas import (
    AccountOut,
    CategoryComparison,
    CategorySpend,
    GoalCreate,
    GoalOut,
    GoalUpdate,
    MerchantSpend,
    NetWorthPoint,
    SummaryResponse,
    TransactionOut,
    TransactionUpdate,
    TrendPoint,
)

router = APIRouter(prefix="/api/finance", tags=["finance"])

# Account types whose Plaid "current" balance represents money owed, not held.
LIABILITY_TYPES = {"credit", "loan"}

# Categories excluded from "spending" totals everywhere.
NON_SPEND_CATEGORIES = ["Income", "Transfers"]


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


@router.patch("/transactions/{txn_id}", response_model=TransactionOut)
def recategorize_transaction(
    txn_id: int, payload: TransactionUpdate, db: Session = Depends(get_db)
):
    """Set a transaction's category and persist it as a durable merchant rule that
    also reassigns other past/future transactions from the same merchant."""
    txn = db.get(Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.category = payload.category
    key = match_key(txn.merchant_name, txn.name)
    if key is not None:
        upsert_rule_and_apply(db, key, payload.category)
    db.commit()
    db.refresh(txn)
    return txn


@router.get("/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db)):
    """Known category names (seed list + any in use) for the recategorize picker."""
    seeded = {c.name for c in db.query(Category).all()}
    used = {row[0] for row in db.query(Transaction.category).distinct().all() if row[0]}
    return sorted(seeded | used)


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


def _bucket_start(d: date, granularity: str) -> date:
    """Snap a date to the start of its bucket."""
    if granularity == "month":
        return d.replace(day=1)
    if granularity == "week":
        return d - timedelta(days=d.weekday())  # Monday
    return d  # day


@router.get("/spending-trend", response_model=list[TrendPoint])
def spending_trend(
    period: int = Query(180, ge=1, le=1095, description="Look-back window in days"),
    granularity: str = Query("month", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
):
    """Spend vs. income bucketed over time. Powers the trend / cash-flow chart."""
    since = date.today() - timedelta(days=period)
    txns = (
        db.query(Transaction.date, Transaction.amount, Transaction.category)
        .filter(Transaction.date >= since)
        .all()
    )

    spent: dict[date, float] = defaultdict(float)
    income: dict[date, float] = defaultdict(float)
    for txn_date, amount, category in txns:
        bucket = _bucket_start(txn_date, granularity)
        if category == "Income" or amount < 0:
            # Income category, or a credit (negative = money in) in any bucket.
            income[bucket] += -amount if amount < 0 else amount
        elif category not in NON_SPEND_CATEGORIES:
            spent[bucket] += amount

    buckets = sorted(set(spent) | set(income))
    return [
        TrendPoint(
            period_start=b,
            spent=round(spent.get(b, 0.0), 2),
            income=round(income.get(b, 0.0), 2),
        )
        for b in buckets
    ]


@router.get("/top-merchants", response_model=list[MerchantSpend])
def top_merchants(
    period: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Where the money actually goes — merchant_name is synced but never surfaced."""
    since = date.today() - timedelta(days=period)
    label = func.coalesce(Transaction.merchant_name, Transaction.name, "Unknown")
    rows = (
        db.query(label, func.sum(Transaction.amount), func.count(Transaction.id))
        .filter(
            Transaction.date >= since,
            Transaction.amount > 0,
            Transaction.category.notin_(NON_SPEND_CATEGORIES),
        )
        .group_by(label)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
        .all()
    )
    return [
        MerchantSpend(merchant=m, total=round(tot, 2), count=cnt) for m, tot, cnt in rows
    ]


@router.get("/category-comparison", response_model=list[CategoryComparison])
def category_comparison(
    days: int = Query(30, ge=1, le=365, description="Length of each comparison window"),
    db: Session = Depends(get_db),
):
    """Per-category spend for the current window vs. the immediately prior one."""
    today = date.today()
    cur_start = today - timedelta(days=days)
    prev_start = today - timedelta(days=days * 2)

    def totals(start: date, end: date) -> dict[str, float]:
        rows = (
            db.query(Transaction.category, func.sum(Transaction.amount))
            .filter(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.amount > 0,
                Transaction.category.notin_(NON_SPEND_CATEGORIES),
            )
            .group_by(Transaction.category)
            .all()
        )
        return {(cat or "Uncategorized"): float(tot) for cat, tot in rows}

    current = totals(cur_start, today)
    previous = totals(prev_start, cur_start)

    out: list[CategoryComparison] = []
    for cat in sorted(set(current) | set(previous)):
        cur = round(current.get(cat, 0.0), 2)
        prev = round(previous.get(cat, 0.0), 2)
        pct = round((cur - prev) / prev * 100, 1) if prev else None
        out.append(CategoryComparison(category=cat, current=cur, previous=prev, pct_change=pct))
    out.sort(key=lambda c: c.current, reverse=True)
    return out


@router.get("/net-worth", response_model=list[NetWorthPoint])
def net_worth(
    period: int = Query(180, ge=1, le=1095),
    db: Session = Depends(get_db),
):
    """Net worth over time from daily balance snapshots. Empty until snapshots
    accrue (see the daily scheduler / sync). Investment holdings are added to the
    latest point via the investments seam when available."""
    since = date.today() - timedelta(days=period)
    account_type = {a.id: (a.type or "").lower() for a in db.query(Account).all()}

    snaps = (
        db.query(BalanceSnapshot)
        .filter(BalanceSnapshot.date >= since)
        .order_by(BalanceSnapshot.date)
        .all()
    )
    if not snaps:
        return []

    # For each date a snapshot exists, carry forward each account's latest balance.
    dates = sorted({s.date for s in snaps})
    latest: dict[int, float] = {}
    by_date: dict[date, list[BalanceSnapshot]] = defaultdict(list)
    for s in snaps:
        by_date[s.date].append(s)

    points: list[NetWorthPoint] = []
    for d in dates:
        for s in by_date[d]:
            latest[s.account_id] = s.balance or 0.0
        assets = sum(
            bal for aid, bal in latest.items() if account_type.get(aid) not in LIABILITY_TYPES
        )
        liabilities = sum(
            bal for aid, bal in latest.items() if account_type.get(aid) in LIABILITY_TYPES
        )
        points.append(
            NetWorthPoint(
                date=d,
                assets=round(assets, 2),
                liabilities=round(liabilities, 2),
                net_worth=round(assets - liabilities, 2),
            )
        )

    # Fold live investment value into the most recent point, if linked.
    portfolio = get_portfolio_value(db)
    if portfolio is not None and points:
        last = points[-1]
        last.assets = round(last.assets + portfolio, 2)
        last.net_worth = round(last.net_worth + portfolio, 2)

    return points


def _project_goal(goal: Goal, db: Session) -> GoalOut:
    """Compound-growth projection: current portfolio + monthly contributions grown
    at the assumed annual return until target_date."""
    current = get_portfolio_value(db)
    base = GoalOut.model_validate(goal).model_copy(
        update={
            "current_value": current,
            "projected_value": None,
            "gap": None,
            "on_track": None,
            "required_monthly_contribution": None,
        }
    )
    if current is None:
        return base  # investments not linked yet — projection unavailable

    months = max(0.0, (goal.target_date - date.today()).days / 30.4375)
    r = (1 + goal.expected_annual_return) ** (1 / 12) - 1  # monthly rate
    growth = (1 + r) ** months
    pmt = goal.monthly_contribution

    if abs(r) < 1e-9:
        fv = current + pmt * months
        annuity_factor = months
    else:
        annuity_factor = (growth - 1) / r
        fv = current * growth + pmt * annuity_factor

    # PMT needed to exactly hit target (clamped at 0 if already on track).
    if annuity_factor > 0:
        needed = (goal.target_amount - current * growth) / annuity_factor
    else:
        needed = 0.0

    return base.model_copy(
        update={
            "projected_value": round(fv, 2),
            "gap": round(fv - goal.target_amount, 2),
            "on_track": fv >= goal.target_amount,
            "required_monthly_contribution": round(max(0.0, needed), 2),
        }
    )


@router.get("/goals", response_model=list[GoalOut])
def list_goals(db: Session = Depends(get_db)):
    return [_project_goal(g, db) for g in db.query(Goal).order_by(Goal.target_date).all()]


@router.post("/goals", response_model=GoalOut, status_code=201)
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)):
    goal = Goal(**payload.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _project_goal(goal, db)


@router.patch("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, payload: GoalUpdate, db: Session = Depends(get_db)):
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    for key, val in payload.model_dump(exclude_unset=True).items():
        setattr(goal, key, val)
    db.commit()
    db.refresh(goal)
    return _project_goal(goal, db)


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    db.commit()
