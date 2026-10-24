# Investments integration contract

Two sides touch investment data:

- **Producer:** the investments module (`app/investments/`, `routers/investments.py`)
  syncs holdings from Plaid and values them.
- **Consumer:** the finance code, whose retirement-goal projection needs the
  portfolio value.

They meet at a single narrow seam. The finance side imports nothing else across the
boundary, so either side can change its internals freely. (It began as the contract
that let the two be built in parallel branches.)

## The seam

```python
# backend/app/investments/portfolio.py
from sqlalchemy.orm import Session

def get_portfolio_value(db: Session) -> float | None:
    """Total current value across all investment accounts.
    Returns None when no investment source is linked."""
```

- **Owner:** the investments module, which implements it.
- **Consumer:** the goals endpoint in `routers/finance.py` imports **only** this function.
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

## Consumers

- `app/routers/finance.py` → `net-worth` does **not** add portfolio value.
  Balance snapshots already carry every account's `current_balance`, investment
  accounts included, so adding the seam on top counted the whole portfolio twice
  on the latest point. It stayed hidden only while holdings were valued at 0.
- `app/routers/finance.py` → `goals` projection uses it as the retirement
  goal's `current_value`; falls back to a "connect investments" state when None.
