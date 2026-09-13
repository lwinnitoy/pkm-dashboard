"""Background scheduler for periodic jobs (daily balance snapshots and, when
configured, automatic Plaid transaction sync).

Kept tiny: one module-level BackgroundScheduler started/stopped by the FastAPI
lifespan. SQLite access from the job thread is fine because the engine is built
with check_same_thread=False (see database.py). Note: this runs in-process, so an
always-on deployment (e.g. a Reserved VM) is required for these jobs to fire —
an autoscale/scale-to-zero deployment would suspend them."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.database import SessionLocal
from app.models import PlaidItem
from app.routers.plaid import sync_all_items
from app.snapshots import run_daily_snapshot

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_scheduled_sync() -> None:
    """Automatic sync tick: sync every linked item, swallowing errors so a
    transient Plaid failure never crashes the scheduler thread."""
    with SessionLocal() as db:
        if db.query(PlaidItem).first() is None:
            return
        try:
            totals = sync_all_items(db)
            logger.info("scheduled sync complete: %s", totals)
        except Exception:  # noqa: BLE001 - keep the scheduler alive
            logger.exception("scheduled sync failed")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    settings = get_settings()
    _scheduler = BackgroundScheduler(timezone="UTC")

    # Once a day, just after midnight UTC: balance snapshot for net-worth history.
    _scheduler.add_job(
        run_daily_snapshot,
        CronTrigger(hour=0, minute=5),
        id="daily_balance_snapshot",
        replace_existing=True,
        misfire_grace_time=3600,  # run if the process was down at the scheduled minute
    )

    # Optional automatic transaction sync (disabled unless SYNC_INTERVAL_HOURS > 0).
    if settings.sync_interval_hours > 0:
        _scheduler.add_job(
            run_scheduled_sync,
            IntervalTrigger(hours=settings.sync_interval_hours),
            id="auto_sync",
            replace_existing=True,
            misfire_grace_time=3600,
        )

    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
