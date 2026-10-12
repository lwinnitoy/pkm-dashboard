"""Standalone maintenance job: sync transactions and investments, then refresh
balances + snapshot.

For hosts where the in-process APScheduler can't stay always-on (Cloud Run scales
to zero), run this on a schedule instead. In production that's the daily Cloud
Run Job (deploy/cloudrun/job.sh); anywhere else, any external cron:

    cd backend && python -m app.jobs

It reuses the same code paths as the manual "Sync now" button and the daily
snapshot, and is idempotent (safe to run repeatedly). Each step runs even if an
earlier one failed, so a Plaid outage never costs a day of net-worth history;
the exit status is non-zero if any step failed.
"""
import logging
import sys

from app.database import SessionLocal
from app.routers.investments import sync_all_investments
from app.routers.plaid import sync_all_items
from app.snapshots import run_daily_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jobs")


def run() -> bool:
    """Run every step; True if all of them succeeded."""
    ok = True

    def step(name, fn):
        nonlocal ok
        try:
            result = fn()
            logger.info("%s complete%s", name, f": {result}" if result is not None else "")
        except Exception:
            ok = False
            logger.exception("%s failed", name)

    def with_session(sync):
        def go():
            with SessionLocal() as db:
                return sync(db)

        return go

    step("transaction sync", with_session(sync_all_items))
    step("investments sync", with_session(sync_all_investments))
    # Own session inside: pull fresh balances from Plaid, then snapshot the day.
    # Runs with nothing linked too, so CSV-imported accounts still get history.
    step("balance snapshot", run_daily_snapshot)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
