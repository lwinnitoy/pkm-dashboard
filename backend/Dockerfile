# Backend image: FastAPI under uvicorn. Runs Alembic migrations on start so the
# schema is always current before the app serves traffic.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ ./

EXPOSE 8000

# `alembic upgrade head` is idempotent and the source of truth on Postgres; on a
# fresh SQLite volume it simply creates the schema.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
