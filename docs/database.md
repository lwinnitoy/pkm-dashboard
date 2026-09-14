# Database & migrations

The app runs on **SQLite** locally and **Postgres** in the cloud. Both are driven
by `DATABASE_URL` (in `backend/.env`); the schema is defined once by the SQLAlchemy
models in `app/models.py` and managed by **Alembic**.

## How the schema is managed per environment

| Environment | `DATABASE_URL` | Schema created by |
|-------------|----------------|-------------------|
| Local dev   | `sqlite:///./pkm.db` | `create_all` on app boot (zero setup) |
| Cloud       | `postgresql+psycopg://…` | `alembic upgrade head` (migration history) |

`app/main.py` only calls `create_all` when the dialect is SQLite, so Postgres never
races with or drifts from the migration history. Alembic reads the same
`DATABASE_URL` (wired in `alembic/env.py`), so migration commands always target the
DB the app uses.

## Everyday commands

Run from `backend/` with the project venv (e.g. `../.venv/bin/alembic`):

```bash
alembic upgrade head            # apply all migrations (run this on deploy)
alembic revision --autogenerate -m "describe change"   # after editing models.py
alembic downgrade -1            # roll back one migration
alembic current                 # show the DB's current revision
alembic history                 # list migrations
```

After autogenerating, **read the generated file** — Alembic can't always infer
renames or data migrations. Encrypted columns (`EncryptedString`) are handled: a
`render_item` hook in `env.py` emits the right import automatically.

## Pointing at a cloud Postgres (Neon / Supabase)

1. Create a database, copy its connection string, and convert the scheme to the
   psycopg driver: `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require`
2. Put it in `backend/.env` as `DATABASE_URL`.
3. Install the driver (already in requirements): `pip install -r backend/requirements.txt`
4. Create the schema: `alembic upgrade head`
5. Start the app — category seeding runs on boot against the migrated schema.

## Migrating an existing local SQLite DB to Alembic tracking

A dev `pkm.db` created by `create_all` has no `alembic_version` table. To bring it
under Alembic without recreating it, stamp it at the initial revision:

```bash
alembic stamp head
```

New model changes then flow through `alembic revision --autogenerate` like any other.
