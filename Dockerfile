# Single-container image for Google Cloud Run (see docs/deploy-cloud-run.md).
#
# FastAPI serves the built UI itself (app/main.py mounts frontend/dist), so the
# whole app is one service on one port, same origin, no CORS. The same image runs
# the daily Cloud Run Job (deploy/cloudrun/job.sh). The docker-compose stack keeps
# its separate backend/ and frontend/ images.

FROM node:22-alpine AS ui
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Empty base = same-origin "/api/..." requests.
ENV VITE_API_BASE=""
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# - postgresql-client: pg_dump for the job's nightly backup. Taken from the
#   PostgreSQL project's apt repo because pg_dump refuses to dump a server newer
#   than itself, and Debian's client lags behind what Neon runs.
# - tzdata: so TZ=America/Vancouver makes the app's date.today() local. Without it,
#   "today" is UTC and flips to tomorrow at 5 pm Pacific.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg tzdata \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get purge -y --auto-remove curl gnupg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --require-hashes -r backend/requirements.txt
COPY backend/ backend/
COPY deploy/cloudrun/job.sh deploy/cloudrun/job.sh
COPY --from=ui /src/frontend/dist frontend/dist

# Run as an unprivileged user. The code stays root-owned (read-only to the app),
# and nothing is written to disk at runtime: Postgres holds the data and
# PYTHONDONTWRITEBYTECODE skips .pyc files. The job's backup bucket is mounted
# with uid/gid 10001 so this user can write the dump (docs/deploy-cloud-run.md).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
USER app

WORKDIR /srv/backend
# Migrations run on start. Cloud Run is deployed with
# --max-instances=1, so two instances never race the same upgrade.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
