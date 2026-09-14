# pkm-platform

A self-hosted "personal cloud" to manage your life. **v1 is a finances MVP**: sync
bank/credit-card transactions via [Plaid](https://plaid.com), categorize them, and view
spending on a dashboard. Tasks, subscriptions, and calendar modules are planned to build on
the same foundation.

## Stack

- **Backend:** Python / FastAPI + SQLAlchemy (SQLite for local dev)
- **Frontend:** React + TypeScript (Vite), `react-plaid-link`, `recharts`
- **Bank data:** Plaid — built against **Sandbox** (free mock data); switch to the free
  **Trial plan** (10 live Production Items) for real accounts.

## Prerequisites

- Python 3.11+ and Node 18+
- A free Plaid account → `client_id` + Sandbox `secret` from
  [dashboard.plaid.com](https://dashboard.plaid.com) → Team Settings → Keys.

## Setup & run

### Backend

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

cd backend
cp .env.example .env                     # paste your PLAID_CLIENT_ID / PLAID_SECRET
../.venv/bin/uvicorn app.main:app        # http://localhost:8000  (docs at /docs)
```

Tip: `source .venv/bin/activate` first, then you can just run `uvicorn app.main:app`.
The SQLite DB (`pkm.db`) and category seed data are created automatically on first boot.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_BASE defaults to http://localhost:8000
npm run dev                   # http://localhost:5173
```

## Using it

1. Open the dashboard → **Connect a bank**. In Sandbox, use any test institution with
   credentials `user_good` / `pass_good`.
2. Click **Sync now** to pull transactions via Plaid's `/transactions/sync`.
3. The dashboard shows total spend, a per-category breakdown, and recent transactions.

To go live: set `PLAID_ENV=production` (on a Plaid Trial plan) and re-link your real
institution.

## How the Plaid sync works

`create-link-token` → Plaid Link (user auth) → `exchange-token` (stores `access_token`) →
`sync` (cursor-based incremental fetch; Plaid returns `added`/`modified`/`removed`, so dedup
is handled by the cursor rather than by us).

## Connecting Wealthsimple / Canadian investment accounts

Plaid supports Wealthsimple (Canada). Link is initialized with `transactions` as the
primary product (so the institution list isn't over-filtered) and `investments` in
`PLAID_ADDITIONAL_CONSENTED_PRODUCTS`, which captures investment consent *if* the
institution supports it — without hiding institutions that don't. Requires
`PLAID_ENV=production` (Wealthsimple isn't in Sandbox) and `CA` in `PLAID_COUNTRY_CODES`.

Cash/spending transactions sync through `/transactions/sync`; investment **holdings** and
investment transactions (buys/sells/dividends) sync through the **investments module**
(`/api/investments/*`, backed by Plaid's `/investments/holdings/get` and
`/investments/transactions/get`). Endpoints:

- `POST /api/investments/sync` — best-effort per item (items without investment accounts
  are skipped, not errored); upserts securities/holdings/transactions (idempotent).
- `GET /api/investments/holdings` — current positions with security + account info.
- `GET /api/investments/transactions` — paginated investment transactions.
- `GET /api/investments/portfolio` — total value, value by account, top holdings.

## Project layout

- `backend/app/models.py` — `plaid_items`, `accounts`, `transactions`, `categories`
- `backend/app/routers/plaid.py` — link / exchange / sync
- `backend/app/routers/finance.py` — spending dashboard read endpoints
- `backend/app/routers/investments.py` — investments sync + holdings/portfolio endpoints
- `frontend/src/` — `api/` client, `components/`, `pages/Dashboard.tsx`

## Roadmap / hardening TODOs

- ~~Encrypt `access_token` at rest~~ ✅ done — Fernet-encrypted via `EncryptedString`
  (`app/crypto.py`); requires `SECRET_ENCRYPTION_KEY` in `.env`.
- Scheduled background sync (APScheduler) — currently manual via "Sync now".
- Docker Compose + hosting.
- Future modules: tasks, subscriptions engine, calendar sync.
```
