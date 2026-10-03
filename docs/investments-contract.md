# Investments integration contract

Two worktrees touch investment data:

- **`feature/dashboard`** (this branch) — consumes portfolio value for the
  retirement-goal projection and the net-worth chart.
- **Wealthsimple worktree** — produces portfolio value by syncing holdings.

To let both branches build in parallel and merge cleanly, they agree on a single
narrow seam. Neither side imports anything else across the boundary.

## The seam

```python
# backend/app/investments/portfolio.py
from sqlalchemy.orm import Session

def get_portfolio_value(db: Session) -> float | None:
    """Total current value across all investment accounts.
    Returns None when no investment source is linked."""
```

- **Owner:** the Wealthsimple worktree replaces the stub with the real query.
- **Consumer:** `feature/dashboard` imports **only** this function.
- **Contract:** signature and return semantics above are frozen. Returning
  `None` (not `0.0`) means "no investments linked" (no investment accounts and
  no holdings) so the UI can show an empty state instead of a misleading zero
  line.

## What the number is

The sum over investment accounts (type `investment`, plus any account holding
securities) of each account's value:

- its `current_balance` when Plaid gave one. For an investment account that
  balance is the institution's own total, uninvested cash included, so it's the
  authoritative figure;
- otherwise the sum of its holdings that could be priced.

Per-holding prices go through a fallback chain in
`app/investments/valuation.py` (institution price → security close price →
latest buy/sell in the account, currency-guarded). That chain matters for the
holdings table, gain and allocation, but rarely for this total, because
Wealthsimple reports every holding's institution price as 0 while the account
balance is correct. `/api/investments/portfolio`'s `total_value` is computed by
the same `value_portfolio()` call, so the endpoint and the seam can't drift.

## Consumers on this branch

- `app/routers/finance.py` → `net-worth` does **not** add portfolio value.
  Balance snapshots already carry every account's `current_balance`, investment
  accounts included, so adding the seam on top counted the whole portfolio twice
  on the latest point. It stayed hidden only while holdings were valued at 0.
- `app/routers/finance.py` → `goals` projection uses it as the retirement
  goal's `current_value`; falls back to a "connect investments" state when None.

## Merge notes

The Wealthsimple branch will add its own models/router; it should keep them under
`app/investments/` and register its router in `app/main.py`. The only file both
branches edit is `main.py` (router registration) — keep those additions on
separate lines to minimize conflicts.
