# Hosting

> **Production runs on Google Cloud Run + Neon**, with Google sign-in (IAP) in front
> and a daily Cloud Run Job for backups and sync. Step by step:
> [deploy-cloud-run.md](deploy-cloud-run.md). Why that shape:
> [hosting-options.md](hosting-options.md). This page covers the other way to run
> it: Docker Compose, on your own machine or a box you control.

## Two ways the app is packaged

- **One container** (root [Dockerfile](../Dockerfile)), used by Cloud Run. The UI is
  built to static files and FastAPI serves them next to the API (`mount_frontend`
  in `app/main.py`), so everything is on one port.
- **Two containers plus Postgres** ([docker-compose.yml](../docker-compose.yml)): the
  backend image (`backend/Dockerfile`) and an nginx-served frontend that
  reverse-proxies `/api` to it. Use this for a local production-like run, or to
  self-host on a single box.

Both run `alembic upgrade head` before starting, so the schema is created or updated
before any traffic arrives.

## Secrets

Auth and encryption are **required** for anything reachable from a network. In
`backend/.env` (or your host's secret store) set:

| Var | Why | Generate |
|-----|-----|----------|
| `SECRET_ENCRYPTION_KEY` | Fernet key encrypting Plaid tokens at rest | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `APP_PASSWORD` | Turns on the login screen (the API is open if blank) | a long random passphrase |
| `PLAID_CLIENT_ID` / `PLAID_SECRET` / `PLAID_ENV=production` | Live bank data | Plaid dashboard |

`AUTH_SECRET` is optional (defaults to `SECRET_ENCRYPTION_KEY`). Compose sets
`DATABASE_URL` to its bundled Postgres.

## Local production-like run

```bash
cp backend/.env.example backend/.env   # fill in the secrets above
docker compose up --build              # app at http://localhost:8080
```

`docker compose config` validates the file without starting anything.

## Self-hosting on one box

Copy the repo to a VPS, set `backend/.env`, and run `docker compose up -d --build`
behind a TLS-terminating reverse proxy (Caddy or Traefik) pointed at the `frontend`
service. Two things the Cloud Run setup does for you that you'd do here yourself:

- **Sync.** The box is always on, so the in-process scheduler can sync: set
  `SYNC_INTERVAL_HOURS` (e.g. `6`). The daily balance snapshot runs either way. Or
  leave it at `0` and cron `cd backend && python -m app.jobs` instead.
- **Backups.** Schedule a `pg_dump` off the box. Net-worth history comes from daily
  balance snapshots, which Plaid can't give back. The restore steps in
  [deploy-cloud-run.md](deploy-cloud-run.md#day-to-day) work for any Postgres.

For a managed Postgres instead of the bundled one, see [database.md](database.md).
