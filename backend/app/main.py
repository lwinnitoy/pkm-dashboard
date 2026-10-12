"""FastAPI entrypoint: create tables, seed categories and insights, register routers."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.auth import require_auth
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.insights import store as insights_store
from app.models import Category
from app.plaid_client import DEFAULT_CATEGORIES
from app.routers import auth, budgets, finance, imports, insights, investments, plaid
from app.routers.imports import MAX_UPLOAD_BYTES
from app.scheduler import shutdown_scheduler, start_scheduler

# Uvicorn configures only its own loggers; without this, the app's INFO logs
# (sync results, scheduler ticks) are silently dropped.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _seed_categories() -> None:
    with SessionLocal() as db:
        existing = {c.name for c in db.query(Category).all()}
        for name in DEFAULT_CATEGORIES:
            if name not in existing:
                db.add(Category(name=name))
        db.commit()


def _seed_insights() -> None:
    """Sync the shipped learning cards from app/insights/content/*.yaml.

    Best-effort: reading material is not worth failing boot over, so a bad edit
    to a content file is logged and the finance app still starts.
    (tests/test_insights.py validates the shipped files, which is where a bad
    edit should be caught.)
    """
    try:
        cards = insights_store.load_seed()
        with SessionLocal() as db:
            insights_store.sync_seed(db, cards)
            db.commit()
    except Exception:
        logger.exception("insight seed sync failed; continuing without it")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # SQLite (local dev) bootstraps its schema on boot for zero setup. Postgres
    # (cloud) is migration-managed: run `alembic upgrade head` on deploy instead,
    # so create_all never races or drifts from the migration history.
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(bind=engine)
    _seed_categories()
    _seed_insights()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(title="Ledger API", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The API docs describe every endpoint; with a password set they're for signed-in
# use only, and the simplest rule is to not serve them at all. Checked per request
# so it follows the live setting.
_DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


@app.middleware("http")
async def hide_docs_when_auth_is_on(request: Request, call_next):
    if request.url.path in _DOC_PATHS and get_settings().auth_enabled:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return await call_next(request)


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Refuse a statement upload by its declared size before the body is read:
    the route's own check runs only after FastAPI has spooled the whole file."""
    if request.url.path.startswith("/api/imports/") and request.method == "POST":
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + 64 * 1024:  # + form overhead
            return JSONResponse({"detail": "File larger than 10MB"}, status_code=413)
    return await call_next(request)


# /api/auth/* and /health stay open; all data routers require a valid token
# (a no-op when APP_PASSWORD is unset, i.e. local dev).
app.include_router(auth.router)
_protected = [Depends(require_auth)]
app.include_router(plaid.router, dependencies=_protected)
app.include_router(finance.router, dependencies=_protected)
app.include_router(budgets.router, dependencies=_protected)
app.include_router(investments.router, dependencies=_protected)
app.include_router(imports.router, dependencies=_protected)
app.include_router(insights.router, dependencies=_protected)


@app.get("/health")
def health():
    """Liveness for Cloud Run's startup probe and uptime checks: up only if the
    database answers. Open without auth, so it says nothing about the setup."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve a built frontend from `dist`: its files as-is, any other path as the
    SPA's index.html. Register after the API routers so /api/* and /health win."""
    root = dist.resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(status_code=404)
        # The path arrives URL-decoded with any "../" intact (/..%2F..%2F.env), and
        # this route sits outside auth, so only serve files that resolve inside dist.
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)  # favicon, icons, etc.
        return FileResponse(root / "index.html")  # SPA fallback


# Single-port deploys (the Cloud Run image) serve the built frontend from here. A
# no-op in local dev, where Vite serves the UI and frontend/dist doesn't exist.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    mount_frontend(app, _DIST)
