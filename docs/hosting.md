# Hosting

The app ships as two images — a FastAPI backend (migrated on start) and an
nginx-served frontend that reverse-proxies `/api` to the backend — plus Postgres.
[docker-compose.yml](../docker-compose.yml) wires them together for a local
production-like run and is the template for a real deploy.

## Prerequisites: secrets

Auth and encryption are **required** for any exposed deployment. In `backend/.env`
(or your host's secret store) set:

| Var | Why | Generate |
|-----|-----|----------|
| `SECRET_ENCRYPTION_KEY` | Fernet key encrypting Plaid tokens at rest | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `APP_PASSWORD` | Enables single-user login (API is open if blank!) | a long random passphrase |
| `PLAID_CLIENT_ID` / `PLAID_SECRET` / `PLAID_ENV=production` | Live bank data | Plaid dashboard |

`AUTH_SECRET` is optional (defaults to `SECRET_ENCRYPTION_KEY`). `DATABASE_URL` is
set by compose to the bundled Postgres; point it at a managed Postgres for cloud.

## Local production-like run

```bash
cp backend/.env.example backend/.env   # fill in the secrets above
docker compose up --build              # app at http://localhost:8080
```

`docker compose config` validates the file without starting anything. The backend
runs `alembic upgrade head` on start, so the schema is created/updated before it
serves traffic.

## Deploying to a host

Two common shapes:

1. **One box (VPS + Docker Compose).** Copy the repo, set `backend/.env`, run
   `docker compose up -d --build` behind a TLS-terminating reverse proxy (Caddy/
   Traefik) pointed at the `frontend` service. Simplest for a self-hosted personal
   cloud.
2. **Managed platform (Fly.io / Railway / Render).** Deploy the backend image with
   a managed Postgres attached (set `DATABASE_URL` to
   `postgresql+psycopg://…?sslmode=require`); deploy the frontend image (or host the
   static `dist/` on a CDN and point `VITE_API_BASE` at the backend URL).

### Managed Postgres
See [database.md](database.md). In short: create the DB, set `DATABASE_URL` with the
`postgresql+psycopg://` scheme, and the backend applies migrations on boot.

## Still to wire up (tracked)
- **Automatic sync:** currently manual (button) + a daily balance snapshot. Add a
  scheduled `sync_transactions` job (APScheduler) and, once there's a public URL,
  move to Plaid `SYNC_UPDATES_AVAILABLE` webhooks.
- **Backups:** enable automated backups on the managed Postgres — net-worth
  snapshot history cannot be re-fetched from Plaid.
