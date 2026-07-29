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
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your PLAID_CLIENT_ID / PLAID_SECRET
uvicorn app.main:app --reload # http://localhost:8000  (docs at /docs)
```

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

## Project layout

- `backend/app/models.py` — `plaid_items`, `accounts`, `transactions`, `categories`
- `backend/app/routers/plaid.py` — link / exchange / sync
- `backend/app/routers/finance.py` — dashboard read endpoints
- `frontend/src/` — `api/` client, `components/`, `pages/Dashboard.tsx`

## Roadmap / hardening TODOs

- Encrypt `access_token` at rest before any real hosting.
- Scheduled background sync (APScheduler) — currently manual via "Sync now".
- Docker Compose + hosting.
- Future modules: tasks, subscriptions engine, calendar sync.
```
