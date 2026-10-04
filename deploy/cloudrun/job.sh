#!/bin/bash
# Daily Cloud Run Job: Plaid sync + balance snapshot, then a pg_dump backup into
# the Cloud Storage bucket mounted at $BACKUP_DIR (docs/deploy-cloud-run.md).
#
# The backup runs even if the sync fails: a Plaid outage is exactly when you
# don't also want to miss a day's backup. The job still exits non-zero so the
# failure shows up in Cloud Run.
set -uo pipefail

cd /srv/backend

status=0
python -m app.jobs || status=$?

backup_dir="${BACKUP_DIR:-/backups}"
if [ -d "$backup_dir" ]; then
  # The app's URL names the psycopg driver; pg_dump wants plain postgresql://.
  url=$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgres(ql)?(\+psycopg)?://#postgresql://#')
  out="$backup_dir/pkm-$(date +%Y-%m-%d).sql.gz"  # local date (TZ is set on the job)
  if pg_dump --no-owner --no-privileges "$url" | gzip > "$out"; then
    echo "backup written: $out ($(du -h "$out" | cut -f1))"
  else
    echo "backup FAILED" >&2
    rm -f "$out"
    status=1
  fi
else
  echo "no backup volume at $backup_dir; skipping backup" >&2
fi

exit "$status"
