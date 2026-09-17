"""FastAPI entrypoint: create tables, seed categories, register routers."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import require_auth
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Category
from app.plaid_client import DEFAULT_CATEGORIES
from app.routers import auth, budgets, finance, imports, investments, plaid
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

# /api/auth/* and /health stay open; all data routers require a valid token
# (a no-op when APP_PASSWORD is unset, i.e. local dev).
app.include_router(auth.router)
_protected = [Depends(require_auth)]
app.include_router(plaid.router, dependencies=_protected)
app.include_router(finance.router, dependencies=_protected)
app.include_router(budgets.router, dependencies=_protected)
app.include_router(investments.router, dependencies=_protected)
app.include_router(imports.router, dependencies=_protected)


@app.get("/health")
def health():
    return {"status": "ok", "plaid_env": settings.plaid_env}


# Serve the built frontend for single-port deploys (e.g. Replit). No-op in local
# dev, where Vite serves the UI and frontend/dist doesn't exist. Registered after
# the API routers so /api/* and /health always take precedence.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(status_code=404)
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)  # favicon, icons, etc.
        return FileResponse(_DIST / "index.html")  # SPA fallback
