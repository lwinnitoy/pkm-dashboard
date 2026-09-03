"""FastAPI entrypoint: create tables, seed categories, register routers."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Category
from app.plaid_client import DEFAULT_CATEGORIES
from app.routers import budgets, finance, investments, plaid
from app.scheduler import shutdown_scheduler, start_scheduler


def _seed_categories() -> None:
    with SessionLocal() as db:
        existing = {c.name for c in db.query(Category).all()}
        for name in DEFAULT_CATEGORIES:
            if name not in existing:
                db.add(Category(name=name))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # SQLite (local dev) bootstraps its schema on boot for zero setup. Postgres
    # (cloud) is migration-managed: run `alembic upgrade head` on deploy instead,
    # so create_all never races or drifts from the migration history.
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(bind=engine)
    _seed_categories()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(title="PKM Platform API", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plaid.router)
app.include_router(finance.router)
app.include_router(budgets.router)
app.include_router(investments.router)


@app.get("/health")
def health():
    return {"status": "ok", "plaid_env": settings.plaid_env}
