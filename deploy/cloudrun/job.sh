#!/bin/bash
# Daily Cloud Run Job: a pg_dump backup into the Cloud Storage bucket mounted at
# $BACKUP_DIR, then the Plaid sync + balance snapshot (docs/deploy-cloud-run.md).
#
# The backup runs first so nothing the sync does can cost a day's backup: not a
# failure (the sync step's own error doesn't stop the backup) and not a hang
# (a stuck Plaid call can run into the task timeout, which would kill anything
# queued after it). Either step failing still exits non-zero so it shows up in
# Cloud Run.
set -uo pipefail

cd /srv/backend

status=0

backup_dir="${BACKUP_DIR:-/backups}"
if [ -d "$backup_dir" ]; then
  # The app's URL names the psycopg driver; pg_dump wants plain postgresql://.
  url=$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgres(ql)?(\+psycopg)?://#postgresql://#')
  out="$backup_dir/pkm-$(date +%Y-%m-%d).sql.gz"  # local date (TZ is set on the job)
  # gzip -t catches a truncated file that pg_dump's exit status alone would miss.
  if pg_dump --no-owner --no-privileges "$url" | gzip > "$out" && gzip -t "$out"; then
    echo "backup written: $out ($(du -h "$out" | cut -f1))"
  else
    echo "backup FAILED" >&2
    rm -f "$out"
    status=1
  fi
else
  echo "no backup volume at $backup_dir; skipping backup" >&2
fi

python -m app.jobs || status=1

exit "$status"
