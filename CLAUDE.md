# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Ledger**, a self-hosted personal-finance app for one person. It syncs bank, credit-card
and investment accounts via Plaid, imports CSV/Excel statements for banks Plaid can't
link, categorizes transactions, and shows spending, budgets, cash flow, net worth and
retirement-goal projections. The scope is personal finance only; there are no plans for
non-finance modules. (The repo and some identifiers still say `pkm`, from an earlier,
broader plan.)

- **Backend:** Python 3.12+ / FastAPI + SQLAlchemy 2.0 + Alembic (SQLite for local dev, Postgres via `psycopg` in the cloud), `plaid-python`, APScheduler
- **Frontend:** React 19 + TypeScript (Vite), `react-plaid-link`, `recharts`

## Commands

### Backend
```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend && cp .env.example .env      # set PLAID_CLIENT_ID / PLAID_SECRET / SECRET_ENCRYPTION_KEY
../.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000, docs at /docs
```

Dependencies are locked with hashes: edit `backend/requirements.in` (runtime) or
`requirements-dev.in` (adds pytest/httpx), then regenerate **both** locks from `backend/`
with `../.venv/bin/pip-compile --generate-hashes --allow-unsafe --strip-extras
--output-file=requirements.txt requirements.in` (and the same for `requirements-dev`).
The images install `requirements.txt` with `--require-hashes`.

`SECRET_ENCRYPTION_KEY` is required (Fernet). Generate one with:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
On first boot the SQLite DB (`backend/pkm.db`), tables, and category seed data are created
automatically.

Schema changes are **migration-managed with Alembic** (`backend/alembic/versions/`).
SQLite dev bootstraps via `create_all` on boot, but Postgres runs `alembic upgrade head`
on deploy — so any model change needs a migration or cloud will drift. Use
`op.batch_alter_table` when altering an existing column: SQLite can't `ALTER` in place.
Verify with `alembic upgrade head && alembic check` (the latter reports model/migration drift).
Write `downgrade()` defensively: a dev DB built by `create_all` has backend-generated
constraint names, and a half-applied upgrade has missing objects. So look up FKs by their
referred table (not by name) and check that each index/column exists before dropping it.
`b1c4f7a29e3d_add_manual_statement_imports.py` has the pattern. `tests/test_migrations.py` runs
upgrade → `check` → downgrade base → upgrade on every test run.

```bash
cd backend && ../.venv/bin/pytest          # no external services needed
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
`conftest.py` stops settings from reading `backend/.env`, so a local password or Plaid
config can't change test results; Plaid clients are faked per test module.
The **frontend has no tests** — `npm run build` (tsc) and `npm run lint` are the checks.

## Architecture

### Plaid data flow
`POST /api/plaid/create-link-token` → Plaid Link (browser auth) → `POST /api/plaid/exchange-token`
(stores an encrypted `access_token` + upserts accounts) → `POST /api/plaid/sync`.

Sync is **cursor-based incremental** (`/transactions/sync`): Plaid returns
`added`/`modified`/`removed` and a `next_cursor` persisted per `PlaidItem`, so dedup is
handled by the cursor, not by us. Each item's pages are gathered before any are applied,
and each item is synced on its own: one bank failing (e.g. `ITEM_LOGIN_REQUIRED`) lands
in `skipped_details` instead of stopping the rest. `sync_all_items` always ends with
`write_snapshots`, so net-worth history accrues on every sync.

**Re-linking** a bank produces a new Plaid Item with new account *and transaction* ids.
`exchange_token` keeps the existing `PlaidItem` row (matched by institution), re-binds
accounts by mask, and *detaches* the old transactions (`plaid_transaction_id = NULL`,
pending ones deleted). The next sync's `_adopt_detached` matches each re-sent
transaction to its old row by account/date/amount, so history isn't duplicated. The
replaced Item is removed at Plaid (`remove_item`), as is an item whose last account is
deleted, because orphaned Items still count toward the plan's Item limit. Sync is triggered three ways, all through
the same `sync_all_items` path: the "Sync now" button; the in-process APScheduler
(`app/scheduler.py`), which always runs a daily balance snapshot and adds an interval sync
when `SYNC_INTERVAL_HOURS > 0`; and `python -m app.jobs` (sync + investments + snapshot),
for scale-to-zero hosts where the in-process scheduler can't stay up (production: the
daily Cloud Run Job, see [docs/deploy-cloud-run.md](docs/deploy-cloud-run.md)). Every
step of `app.jobs` runs even if an earlier one fails.

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
Exports carry no balance either, so a manual account's balance is an owner-entered
*anchor* (`balance_anchor` as of `balance_anchor_date`) rolled forward by every imported
transaction dated after it (`app/imports/balance.py`); the derived value is stored in
`current_balance`, so snapshots and net worth read both kinds of account the same way.

Two traps this path exposed, both worth knowing before touching spending queries:
**(1)** `category NOT IN (...)` is UNKNOWN for `NULL`, so uncategorized rows get dropped
from totals instead of counted — filter spending with `COUNTS_AS_SPEND` in
`routers/finance.py` (NULL-safe, built on `IS_SPEND_CATEGORY`), and group by its
`CATEGORY_LABEL` rather than the raw column (NULL and the literal "Uncategorized" are one
bucket; grouped apart, a dict keyed by name keeps only one of them). Spending is **net of
refunds**: a negative amount in a real spend category reduces it, while an uncategorized
deposit is income. Code that buckets rows in Python uses the twin `spend_or_income`, so
every view (summary, budgets, merchants, comparison, trend) agrees. **(2)** Importing a card *and* the account that pays it double-books
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
shows an empty state instead of a misleading zero. The goals endpoint in
`routers/finance.py` consumes it; do not import anything else across this boundary. Net
worth deliberately does **not**: balance snapshots already include investment accounts'
balances, so adding the portfolio on top would double-count. Valuation lives in
`app/investments/valuation.py` — account value is the institution's balance, and holdings
are priced by a fallback chain (institution → security close → last trade → unknown),
because Wealthsimple reports zero per-holding prices through Plaid.

### Secrets at rest
Plaid `access_token` uses the `EncryptedString` SQLAlchemy type (`app/crypto.py`) —
transparently Fernet-encrypted on write / decrypted on read, so the rest of the code treats
it as a plain string. Any new sensitive column should reuse `EncryptedString`.

### Auth and deployment
Single-user auth (`app/auth.py`): when `APP_PASSWORD` is set, `/api/auth/login` issues an
`itsdangerous`-signed bearer token, and every data router is mounted with
`Depends(require_auth)` in `app/main.py`. When `APP_PASSWORD` is unset, auth is a no-op
(local dev). New routers should be registered the same protected way. Only `/api/auth/*`
and `/health` stay open.

For single-port deploys (Cloud Run via the root `Dockerfile`), FastAPI also serves
`frontend/dist` (`mount_frontend`), registered *after* the API routers so `/api/*` takes
precedence. That route sits outside auth, so it only serves files that resolve inside
`dist`; keep that check if you touch it. The Docker image runs `alembic upgrade head`
before starting uvicorn. Production is Cloud Run + Neon behind Google sign-in (IAP), with
a daily Cloud Run Job (`deploy/cloudrun/job.sh`) that backs up with `pg_dump` and then
syncs; see [docs/deploy-cloud-run.md](docs/deploy-cloud-run.md). Other hosting details are in
[docs/hosting.md](docs/hosting.md), and database setup is in
[docs/database.md](docs/database.md).

### Insights (reading material on Goals and Budgets)
The learning cards on the Goals and Budgets pages are rows in `insights`, not JSX. Shipped
cards live in `backend/app/insights/content/<page>.yaml` and are synced on every boot
(`_seed_insights`; best-effort, so `tests/test_insights.py` is what validates the files).
Anything that generates content later — a scheduled AI job, a DAG elsewhere — publishes by
key through `PUT /api/insights/{key}` or `app.insights.store.upsert_insight`; the seed
sync never touches non-seed rows. The frontend's `InsightsPanel` only lays cards out and
renders a small Markdown subset as React elements (never raw HTML). See
[docs/insights.md](docs/insights.md).

### Data model shape (`backend/app/models.py`)
`PlaidItem` (one linked institution login) → `Account` → `Transaction` /
`Holding` / `InvestmentTransaction`. Manual accounts have no `PlaidItem`, and their
transactions point to an `ImportBatch` instead. `Security` is referenced by holdings/txns;
`Category` is a seed lookup for normalized categories; `CategoryRule` stores a user
recategorization as a merchant rule, keyed by a normalized match key, so it survives
syncs; `Budget` is a monthly limit per category; `BalanceSnapshot` is the daily per-account
balance (Plaid only exposes *current* balance, so net-worth history accrues going forward);
`Goal` stores retirement-target + projection assumptions only (current value is read live
via the investments seam, never stored). `Insight` is a reading-material card for a page
(see below). Transaction `amount` follows Plaid's convention:
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
data comes from `FinanceProvider`/`useFinance` (the portfolio loads with it, so nothing
renders "not linked" before it has been asked); the Transactions page is the exception
and pages through history itself (`/api/finance/transactions` + `/count`). Dates from the
API are `YYYY-MM-DD` calendar dates — parse them with `parseDate` (`src/lib/dates.ts`), never
`new Date(iso)`, which reads them as UTC midnight and shows the previous day in North
American timezones; likewise take "today"/"this month" from `dayKey`/`monthKey`, not
`toISOString()`. All backend access goes through the typed
`api` object in `src/api/client.ts` (thin `fetch` wrapper) — add new endpoints there
rather than calling `fetch` in components. Note `req()` forces a JSON content-type; file
uploads use the separate `upload()` helper so the browser can set the multipart boundary.

## Direction
[docs/roadmap.md](docs/roadmap.md) records planned work: the rest of automatic
transaction categorization (researched in
[docs/auto-categorization.md](docs/auto-categorization.md); the detailed Plaid category
map is done) and an AI writer for the insight cards. Consult it before making
data-layer decisions that would be awkward to unwind.
