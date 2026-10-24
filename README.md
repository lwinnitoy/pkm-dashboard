# Ledger

A self-hosted personal-finance app for one person. Ledger pulls in your bank,
credit-card and investment accounts, sorts transactions into categories, and shows
where your money goes, what you're worth, and whether you're on track for retirement.
It runs on your own Google Cloud project or your own machine, so the data stays yours.

## What it does

- **Syncs accounts through [Plaid](https://plaid.com).** Bank, credit-card and
  investment accounts (Wealthsimple included). Balances refresh on every sync.
- **Imports statements Plaid can't reach.** Upload a bank's CSV or Excel export
  (RBC has a preset). Ledger previews new rows, duplicates and conflicts before
  writing anything, and flags months missing from your history.
- **Categorizes transactions.** Plaid's categories map onto a small set of
  buckets. A correction becomes a merchant rule that sticks on future syncs and
  imports. Card payments and transfers between your own accounts are kept out of
  both spending and income.
- **Budgets.** Monthly limits per category, with spent and remaining for any month.
- **Cash flow.** Income against spending over time, plus top merchants and a
  category comparison.
- **Net worth.** A daily balance snapshot for every account builds the history.
  Plaid only reports *current* balances, so this history can't be re-downloaded and
  is backed up daily.
- **Investments.** Holdings, cost basis, gain and allocation.
- **Retirement goals.** Projections from your current portfolio, contributions and
  an expected return, alongside reading cards on budgeting and Canadian retirement
  accounts.

## Quick start (local, Plaid Sandbox)

Prerequisites: Python 3.12+, Node 20.19+ (or 22.12+), and a free Plaid account (the
`client_id` and Sandbox `secret` are under **Team Settings → Keys** at
[dashboard.plaid.com](https://dashboard.plaid.com)).

```bash
# Backend: http://localhost:8000 (API docs at /docs)
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
cp .env.example .env      # set PLAID_CLIENT_ID, PLAID_SECRET, SECRET_ENCRYPTION_KEY
../.venv/bin/uvicorn app.main:app --reload
```

```bash
# Frontend: http://localhost:5173
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE defaults to http://localhost:8000
npm run dev
```

On first boot the SQLite database (`backend/pkm.db`), its tables and the category
list are created automatically. Open the app, go to **Accounts → Connect a bank**,
pick any Sandbox institution, sign in with `user_good` / `pass_good`, and press
**Sync now**.

## Configuration

Everything lives in `backend/.env` (see [backend/.env.example](backend/.env.example)).

| Variable | What it does |
|---|---|
| `SECRET_ENCRYPTION_KEY` | **Required.** Fernet key that encrypts Plaid access tokens at rest. Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Keep it stable and backed up: a different key makes every stored token unreadable. |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` | Plaid credentials; `PLAID_ENV` is `sandbox` or `production`. |
| `PLAID_COUNTRY_CODES` | Defaults to `US,CA`. Canadian institutions need `CA`. |
| `PLAID_REDIRECT_URI` | Needed for OAuth banks. Must be HTTPS and exactly match an allowed redirect URI in the Plaid dashboard. |
| `APP_PASSWORD` | Turns on the login screen. Blank means no login, which is fine only on your own machine. |
| `DATABASE_URL` | SQLite by default; a `postgresql+psycopg://…` URL in the cloud. |
| `SYNC_INTERVAL_HOURS` | Automatic sync for an always-on host (`0` = off). |
| `TZ` | Time zone for "today" and "this month". Production uses `America/Vancouver`. |

## Connecting accounts

- **Going live.** Set `PLAID_ENV=production` with production keys. Plaid's free
  Trial plan covers up to 10 linked institutions. Then link your real institutions.
- **Wealthsimple and other investment accounts.** Link asks for `transactions` and
  adds `investments` as an optional consent, so investment accounts come along
  without hiding institutions that don't offer them. Wealthsimple is production-only
  and needs `CA` in `PLAID_COUNTRY_CODES`.
- **Banks Plaid can't link (RBC).** RBC's push-notification sign-in check is
  incompatible with Plaid's background refresh, so linking fails with "your account
  settings are incompatible". Use **Import** with the bank's CSV/Excel export
  instead. Give the account a starting balance, and later imports roll it forward.
  See [docs/statement-imports.md](docs/statement-imports.md).
- **Reconnecting a bank.** When a bank needs you to sign in again, Sync names it
  (`ITEM_LOGIN_REQUIRED`). Link it again from Accounts: the existing accounts and
  their history carry over without duplicates.

## Keeping data fresh

- **Sync now** on the Accounts page pulls new transactions, investments and
  balances, and records today's balance snapshot.
- **The daily job** (`python -m app.jobs`) does the same unattended. In production
  a Cloud Run Job runs it every morning, after a `pg_dump` backup.
- **On an always-on host**, the in-process scheduler takes the daily snapshot, and
  syncs too if `SYNC_INTERVAL_HOURS` is set.

## Deploying

Production runs on **Google Cloud Run + Neon Postgres** behind Google sign-in, for
about $0/month inside the free tiers. A daily Cloud Run Job handles backup and sync.
The full walkthrough, including deploys, rollbacks and **restoring a backup**, is
[docs/deploy-cloud-run.md](docs/deploy-cloud-run.md). Code changes ship with
`deploy/cloudrun/deploy.sh`.

To run it on your own box with Docker Compose instead, see
[docs/hosting.md](docs/hosting.md).

## Development

```bash
cd backend && ../.venv/bin/pytest            # backend tests: no Plaid or network needed
cd frontend && npm run build && npm run lint # type-check, build and lint the UI
```

Schema changes need an Alembic migration (`backend/alembic/versions/`); the test suite
runs the migrations and fails on drift. See [docs/database.md](docs/database.md).

**Layout**
- `backend/app/routers/`: API endpoints: `plaid` (link, sync), `finance` (transactions,
  spending, net worth, goals), `budgets`, `investments`, `imports`, `insights`, `auth`
- `backend/app/imports/`: statement parsing, deduplication and balance roll-forward
- `backend/app/investments/`: holdings valuation and the portfolio-value seam
- `backend/app/jobs.py`: the daily backup-and-sync entry point
- `frontend/src/`: `pages/` (one per nav entry), `components/`, `api/client.ts`

**Docs**
- [deploy-cloud-run.md](docs/deploy-cloud-run.md): production setup, deploys and restores
- [statement-imports.md](docs/statement-imports.md): imports, deduplication, adding a bank preset
- [investments-contract.md](docs/investments-contract.md): how portfolio value is computed and used
- [insights.md](docs/insights.md): the reading cards on Goals and Budgets
- [auto-categorization.md](docs/auto-categorization.md): research for smarter categorization
- [database.md](docs/database.md), [hosting.md](docs/hosting.md), [hosting-options.md](docs/hosting-options.md)
- [roadmap.md](docs/roadmap.md): what's planned next
