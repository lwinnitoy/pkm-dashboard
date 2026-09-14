"""Standalone maintenance job: sync transactions, then refresh balances + snapshot.

For hosts where the in-process APScheduler can't stay always-on (e.g. Replit
Autoscale, which scales to zero), run this on a schedule instead — e.g. a Replit
Scheduled Deployment or any external cron:

    cd backend && python -m app.jobs

It reuses the same code paths as the manual "Sync now" button and the daily
snapshot, and is idempotent (safe to run repeatedly).
"""
import logging

from app.database import SessionLocal
from app.models import PlaidItem
from app.routers.investments import sync_all_investments
from app.routers.plaid import sync_all_items
from app.snapshots import run_daily_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jobs")


def run() -> None:
    with SessionLocal() as db:
        if db.query(PlaidItem).first() is None:
            logger.info("no linked institutions; nothing to sync")
            return
        totals = sync_all_items(db)
        logger.info("transaction sync complete: %s", totals)
        inv = sync_all_investments(db)
        logger.info("investments sync complete: %s", inv)

    # Own session inside: pull fresh balances from Plaid, then snapshot the day.
    run_daily_snapshot()
    logger.info("balance snapshot complete")


if __name__ == "__main__":
    run()
