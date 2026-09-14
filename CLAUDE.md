# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted "personal cloud." **v1 is a finances MVP**: sync bank/credit-card
transactions via Plaid, categorize them, and view spending / net worth / retirement-goal
projections on a dashboard. Tasks, subscriptions, and calendar modules are planned on the
same foundation.

- **Backend:** Python 3.11+ / FastAPI + SQLAlchemy 2.0 (SQLite for local dev), `plaid-python`, APScheduler
- **Frontend:** React 19 + TypeScript (Vite), `react-plaid-link`, `recharts`

## Commands

### Backend
```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend && cp .env.example .env      # set PLAID_CLIENT_ID / PLAID_SECRET / SECRET_ENCRYPTION_KEY
../.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000, docs at /docs
```

`SECRET_ENCRYPTION_KEY` is required (Fernet). Generate one with:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
On first boot the SQLite DB (`backend/pkm.db`), tables, and category seed data are created
automatically — there are **no migrations** (schema changes = delete `pkm.db` in dev, or
add a migration tool before touching production data).

### Frontend
```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE defaults to http://localhost:8000
npm run dev               # http://localhost:5173
npm run build             # tsc -b && vite build
npm run lint              # oxlint
```

There is currently **no automated test suite** (backend or frontend).

## Architecture

### Plaid data flow
`POST /api/plaid/create-link-token` → Plaid Link (browser auth) → `POST /api/plaid/exchange-token`
(stores an encrypted `access_token` + upserts accounts) → `POST /api/plaid/sync`.

Sync is **cursor-based incremental** (`/transactions/sync`): Plaid returns
`added`/`modified`/`removed` and a `next_cursor` persisted per `PlaidItem`, so dedup is
handled by the cursor, not by us. `sync_transactions` also calls `write_snapshots` so
net-worth history accrues on every manual sync. Sync is currently manual (a "Sync now"
button); the only automatic job is a daily balance snapshot.

### Two Plaid data classes, two paths
- **Cash/spending** transactions → `/transactions/sync` → `routers/plaid.py`, read via `routers/finance.py`.
- **Investment holdings + investment transactions** (e.g. Wealthsimple) → `/investments/holdings/get`
  and `/investments/transactions/get` → `routers/investments.py` (`/api/investments/*`).

Link is initialized with `transactions` as the primary product and `investments` as an
*additional consented product* (`PLAID_ADDITIONAL_CONSENTED_PRODUCTS`) — this captures
investment consent when the institution supports it **without filtering the institution
list**. Wealthsimple requires `PLAID_ENV=production` and `CA` in `PLAID_COUNTRY_CODES`
(it is not in Sandbox).

### The investments seam (important boundary)
`backend/app/investments/portfolio.py::get_portfolio_value(db) -> float | None` is the
**only** surface the finance/goals code may use for investment data. See
[docs/investments-contract.md](docs/investments-contract.md) — the signature and return
semantics are frozen. Returning `None` (not `0.0`) means "no investments linked" so the UI
shows an empty state instead of a misleading zero. The net-worth and goals endpoints in
`routers/finance.py` consume it; do not import anything else across this boundary.

### Secrets at rest
Plaid `access_token` uses the `EncryptedString` SQLAlchemy type (`app/crypto.py`) —
transparently Fernet-encrypted on write / decrypted on read, so the rest of the code treats
it as a plain string. Any new sensitive column should reuse `EncryptedString`.

### Data model shape (`backend/app/models.py`)
`PlaidItem` (one linked institution login) → `Account` → `Transaction` /
`Holding` / `InvestmentTransaction`; `Security` is referenced by holdings/txns; `Category`
is a seed lookup for normalized categories; `BalanceSnapshot` is the daily per-account
balance (Plaid only exposes *current* balance, so net-worth history accrues going forward);
`Goal` stores retirement-target + projection assumptions only (current value is read live
via the investments seam, never stored). Transaction `amount` follows Plaid's convention:
**positive = money out**.

### Backend layout conventions
- Routers are thin FastAPI modules under `app/routers/`, each with an `APIRouter(prefix=...)`,
  registered in `app/main.py`. Adding a module = add a router file + one `include_router` line.
- DB access via the `get_db` FastAPI dependency (`app/database.py`); background jobs open
  their own `SessionLocal`. The SQLite engine uses `check_same_thread=False` so the
  scheduler thread can share it.
- Settings come from `.env` via `app/config.py` (pydantic-settings, `get_settings()` is
  `lru_cache`d). Comma-separated env vars are exposed as `*_list` properties.

### Frontend
Single `pages/Dashboard.tsx` composed of chart/table components in `components/`. All
backend access goes through the typed `api` object in `src/api/client.ts` (thin `fetch`
wrapper) — add new endpoints there rather than calling `fetch` in components.
