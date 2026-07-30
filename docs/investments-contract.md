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
    """Total current market value across all investment holdings.
    Returns None when no investment source is linked."""
```

- **Owner:** the Wealthsimple worktree replaces the stub with the real query.
- **Consumer:** `feature/dashboard` imports **only** this function.
- **Contract:** signature and return semantics above are frozen. Returning
  `None` (not `0.0`) means "no investments linked" so the UI can show an empty
  state instead of a misleading zero line.

## Consumers on this branch

- `app/routers/finance.py` → `net-worth` endpoint adds portfolio value to bank
  balances when non-None.
- `app/routers/finance.py` → `goals` projection uses it as the retirement
  goal's `current_value`; falls back to a "connect investments" state when None.

## Merge notes

The Wealthsimple branch will add its own models/router; it should keep them under
`app/investments/` and register its router in `app/main.py`. The only file both
branches edit is `main.py` (router registration) — keep those additions on
separate lines to minimize conflicts.
