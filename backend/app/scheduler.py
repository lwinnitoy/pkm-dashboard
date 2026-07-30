"""Background scheduler for periodic jobs (daily balance snapshots).

Kept tiny: one module-level BackgroundScheduler started/stopped by the FastAPI
lifespan. SQLite access from the job thread is fine because the engine is built
with check_same_thread=False (see database.py)."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.snapshots import run_daily_snapshot

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    # Once a day, just after midnight UTC.
    _scheduler.add_job(
        run_daily_snapshot,
        CronTrigger(hour=0, minute=5),
        id="daily_balance_snapshot",
        replace_existing=True,
        misfire_grace_time=3600,  # run if the process was down at the scheduled minute
    )
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
