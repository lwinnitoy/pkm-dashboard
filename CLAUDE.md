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
automatically.

Schema changes are **migration-managed with Alembic** (`backend/alembic/versions/`).
SQLite dev bootstraps via `create_all` on boot, but Postgres runs `alembic upgrade head`
on deploy — so any model change needs a migration or cloud will drift. Use
`op.batch_alter_table` when altering an existing column: SQLite can't `ALTER` in place.
Verify with `alembic upgrade head && alembic check` (the latter reports model/migration drift).

```bash
cd backend && ../.venv/bin/pytest          # 58 tests, no external services needed
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE defaults to http://localhost:8000
npm run dev               # http://localhost:5173
npm run build             # tsc -b && vite build
npm run lint              # oxlint
```

The backend has a pytest suite (`backend/tests/`) using an in-memory SQLite DB per test
and seeding helpers in `tests/factories.py`; no Plaid credentials or network needed.
The **frontend has no tests** — `npm run build` (tsc) and `npm run lint` are the checks.

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

**Known blocker: RBC.** OAuth is wired up correctly (`PLAID_REDIRECT_URI` set, matches
the Plaid dashboard, `PLAID_ENV=production`, `CA` in `PLAID_COUNTRY_CODES`) but linking
still fails with Plaid's "Your account settings are incompatible" error. This is a
Plaid-side limitation, not an app config issue: RBC's in-app push MFA challenges on every
login instead of remembering a trusted device, and Plaid can't complete an async
refresh-capable Item against that pattern (confirmed via Plaid's own support docs — no
committed fix timeline as of 2026-09). Possible ways around it, none yet tried
successfully: enable "remember this device" in RBC's own sign-in security settings if
available, or see if RBC's login offers a non-push second factor (SMS/security questions)
during the OAuth handoff. Don't spend time re-checking the OAuth/env wiring for this
institution until Plaid or RBC changes something.

### Manual statement imports (the non-Plaid path)
Because RBC can't be linked (above), `app/imports/` loads bank CSV/Excel exports into the
same `Transaction` rows a sync would produce — so categories, rules, budgets and charts
never learn there are two sources. `Account`/`Transaction` carry `source` (`plaid` | `csv`),
and the Plaid id columns are nullable because a manual account has no Plaid identity.

Two traps this path exposed, both worth knowing before touching spending queries:
**(1)** `category NOT IN (...)` is UNKNOWN for `NULL`, so uncategorized rows get dropped
from totals instead of counted — use the NULL-safe `IS_SPEND_CATEGORY` helper in
`routers/finance.py`. **(2)** Importing a card *and* the account that pays it double-books
every payment, so transfer-looking descriptions are auto-categorized `Transfers` and
excluded from spend *and* income (`app/imports/categorize.py`). Account `type` also
matters: `LIABILITY_TYPES` decides asset vs. debt, so a credit card must not be created
as `depository`.

Re-imports are reconciled, not blindly appended: each row gets a deterministic
`import_fingerprint` (a UNIQUE column) over account/date/amount/description **plus an
ordinal within that group**, so overlapping statement periods dedupe while two genuinely
identical same-day purchases both survive. Coverage is tracked as statement *periods*
(`ImportBatch`), which is what makes gap detection ("you have June and August, not July")
possible. Adding a bank = adding a `ColumnMap` preset, not a parser.
See [docs/statement-imports.md](docs/statement-imports.md) — read it before touching
fingerprinting, since the ordinal scheme is load-bearing and easy to "simplify" wrongly.

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
Pages under `src/pages/` (one per nav entry, routed in `App.tsx` and listed in
`components/layout/nav.ts`) composed of chart/table components in `components/`. Shared
data comes from `FinanceProvider`/`useFinance`. All backend access goes through the typed
`api` object in `src/api/client.ts` (thin `fetch` wrapper) — add new endpoints there
rather than calling `fetch` in components. Note `req()` forces a JSON content-type; file
uploads use the separate `upload()` helper so the browser can set the multipart boundary.

## Direction
[docs/roadmap.md](docs/roadmap.md) records planned work that isn't started — an email
recap module and an eventual Databricks migration for the analytics layer. Consult it
before making data-layer decisions that would be awkward to unwind.
