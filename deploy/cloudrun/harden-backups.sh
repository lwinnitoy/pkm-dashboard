#!/bin/bash
# One-time hardening of an existing Cloud Run setup's backups. Safe to re-run.
# See docs/deploy-cloud-run.md ("Hardening an existing setup").
#
# Before: the web service and the daily job shared one service account with
# objectAdmin on the backup bucket, so anything that compromised the web app could
# delete every backup, and a deleted backup was gone for good.
# After:
#   - the daily job runs as its own account, which can write and read backups;
#   - the web service has no access to the bucket at all;
#   - a deleted object stays recoverable for 30 days (soft delete);
#   - the bucket mounts with uid/gid 10001, the image's unprivileged user.
#
# Run it, then deploy (deploy/cloudrun/deploy.sh) and execute the job once:
#   gcloud run jobs execute pkm-daily --region us-west1 --wait
set -euo pipefail

PROJECT_ID=${PROJECT_ID:-pkm-liamwinnitoy}
REGION=${REGION:-us-west1}
JOB=${JOB:-pkm-daily}
BUCKET=${BUCKET:-$PROJECT_ID-backups}
RUN_SA=pkm-run@$PROJECT_ID.iam.gserviceaccount.com
JOB_SA=pkm-job@$PROJECT_ID.iam.gserviceaccount.com
APP_UID=10001  # matches `useradd --uid` in the Dockerfile

gcloud config set project "$PROJECT_ID" >/dev/null

echo "==> job service account"
if ! gcloud iam service-accounts describe "$JOB_SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create pkm-job --display-name="pkm daily job"
fi
# The job reads the same secrets as the app (DATABASE_URL, Plaid, encryption key).
gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None \
  --member="serviceAccount:$JOB_SA" --role=roles/secretmanager.secretAccessor >/dev/null

echo "==> bucket access: job writes and reads, the web app gets nothing"
# objectCreator can add objects but not overwrite or delete them; objectViewer
# lets the mount list the bucket and job.sh verify the file it just wrote.
# A just-created service account takes a minute or two to reach Cloud Storage,
# which rejects it as "does not exist" until then; retry instead of failing.
bind_bucket_role() {
  local role=$1 attempt
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
        --member="serviceAccount:$JOB_SA" --role="$role" >/dev/null 2>&1; then
      return 0
    fi
    echo "    $JOB_SA not visible to Cloud Storage yet; retrying in 10s ($attempt/12)"
    sleep 10
  done
  # Last try without hiding the error, so a real problem is visible.
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --member="serviceAccount:$JOB_SA" --role="$role" >/dev/null
}
for role in roles/storage.objectCreator roles/storage.objectViewer; do
  bind_bucket_role "$role"
done
gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$RUN_SA" --role=roles/storage.objectAdmin >/dev/null 2>&1 || true

echo "==> 30-day soft delete"
gcloud storage buckets update "gs://$BUCKET" --soft-delete-duration=30d

echo "==> job: own account, bucket mounted for the unprivileged user"
gcloud run jobs update "$JOB" --region "$REGION" \
  --service-account "$JOB_SA" \
  --clear-volume-mounts --clear-volumes \
  --add-volume "name=backups,type=cloud-storage,bucket=$BUCKET,mount-options=uid=$APP_UID;gid=$APP_UID" \
  --add-volume-mount volume=backups,mount-path=/backups

cat <<EOF

Done. Now deploy the non-root image and run the job once:
  deploy/cloudrun/deploy.sh
  gcloud run jobs execute $JOB --region $REGION --wait
  gcloud storage ls gs://$BUCKET      # a new pkm-YYYY-MM-DD-HHMMSS.sql.gz

If the job's backup step fails with a 403 on the bucket, Cloud Storage FUSE needed
to overwrite the object it created. Swap objectCreator for objectUser (which can
delete); the 30-day soft delete still makes any deletion recoverable:
  gcloud storage buckets add-iam-policy-binding gs://$BUCKET \\
    --member=serviceAccount:$JOB_SA --role=roles/storage.objectUser
EOF
