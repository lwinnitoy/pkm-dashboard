# Backend image: FastAPI under uvicorn. Runs Alembic migrations on start so the
# schema is always current before the app serves traffic.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --require-hashes -r requirements.txt

COPY backend/ ./

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
USER app

EXPOSE 8000

# `alembic upgrade head` is idempotent and the source of truth on Postgres. `exec`
# makes uvicorn PID 1, so `docker compose stop` (SIGTERM) shuts it down cleanly.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
