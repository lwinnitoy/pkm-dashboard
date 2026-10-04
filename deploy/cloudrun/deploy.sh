#!/bin/bash
# Deploy the current commit: build it in Cloud Build, roll it out to the app
# (Cloud Run service) and the daily job, tagged with the commit hash so
# "what's live?" and rollbacks are answerable. See docs/deploy-cloud-run.md.
#
#   deploy/cloudrun/deploy.sh            # normal: clean tree, tests must pass
#   deploy/cloudrun/deploy.sh --dirty    # deploy uncommitted work (tagged -dirty)
#   SKIP_TESTS=1 deploy/cloudrun/deploy.sh
set -euo pipefail

PROJECT_ID=${PROJECT_ID:-pkm-liamwinnitoy}
REGION=${REGION:-us-west1}
SERVICE=${SERVICE:-pkm}
JOB=${JOB:-pkm-daily}

cd "$(dirname "$0")/../.."

tag=$(git rev-parse --short HEAD)
if [ -n "$(git status --porcelain)" ]; then
  if [ "${1:-}" != "--dirty" ]; then
    echo "Uncommitted changes: commit first, or pass --dirty to deploy them anyway." >&2
    exit 1
  fi
  tag="$tag-dirty"
fi

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  echo "==> backend tests"
  (cd backend && ../.venv/bin/pytest -q)
fi
# The frontend type-check runs inside the image build (npm run build = tsc + vite).

image="$REGION-docker.pkg.dev/$PROJECT_ID/pkm/app:$tag"
echo "==> building $image"
gcloud builds submit --project "$PROJECT_ID" --tag "$image" .

echo "==> deploying app (migrations run as it starts)"
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --image "$image"
# A rollback pins traffic to an old revision, and pinned traffic survives new
# deploys; route it back to the revision just created.
gcloud run services update-traffic "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --to-latest

echo "==> pointing the daily job at the same image"
gcloud run jobs update "$JOB" --project "$PROJECT_ID" --region "$REGION" --image "$image"

echo "Deployed $tag."
