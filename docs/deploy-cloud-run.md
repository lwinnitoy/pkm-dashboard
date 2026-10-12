# Deploying to Google Cloud Run + Neon

The chosen hosting shape (option 1 in [hosting-options.md](hosting-options.md)):

| Piece | Where | Why |
|---|---|---|
| App (API + UI) | Cloud Run service, one container ([Dockerfile](../Dockerfile)) | Scales to zero; free tier covers a single user |
| Login | Identity-Aware Proxy (IAP) on the service | Google sign-in in front of every request, from any device. `APP_PASSWORD` stays as a second lock |
| Database | Neon Postgres (free) | Wakes on connect, never needs a manual restore |
| Daily backup + sync | Cloud Run Job ([job.sh](../deploy/cloudrun/job.sh)) run by Cloud Scheduler | No outbound restrictions for Plaid; a `pg_dump` goes to Cloud Storage every day |
| Secrets | Secret Manager | Never in the image or the repo |

Expected cost: about $0 inside the free tiers (Cloud Run, Cloud Scheduler's 3 free
jobs, 5 GB of Cloud Storage in `us-west1`, Secret Manager's free operations, Neon
Free). Google still requires a billing account, so set a budget alert (step 2).

Everything below is copy-paste. Run it from the repo root on your Mac.

## 0. Variables

```bash
export PROJECT_ID=pkm-$(whoami)          # must be globally unique; change if taken
export REGION=us-west1                   # Oregon: in GCS's free regions, next to Neon's us-west-2
export SERVICE=pkm
export JOB=pkm-daily
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/pkm/app:initial   # first setup only; see below
export BUCKET=$PROJECT_ID-backups
export YOU=you@gmail.com                 # the Google account allowed to sign in
export RUN_SA=pkm-run@$PROJECT_ID.iam.gserviceaccount.com
```

`$IMAGE` is only for this first setup. After it, `deploy/cloudrun/deploy.sh` tags every
image with its commit hash and points both the service and the job at it, so don't
reuse `$IMAGE` later to recreate the job; take the current image from
`gcloud run services describe $SERVICE --region $REGION --format='value(spec.template.spec.containers[0].image)'`.

## 1. Tools

```bash
brew install --cask google-cloud-sdk
gcloud auth login
docker info >/dev/null && echo "docker ok"   # Docker Desktop must be running for step 4
```

## 2. Project, billing, APIs

```bash
gcloud projects create $PROJECT_ID
gcloud config set project $PROJECT_ID
```

In the console, link a billing account to the project (**Billing → Link a billing
account**). Then add a budget alert, e.g. $5/month (**Billing → Budgets & alerts**),
so any surprise shows up as an email.

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  cloudscheduler.googleapis.com iap.googleapis.com storage.googleapis.com
gcloud artifacts repositories create pkm --repository-format=docker --location=$REGION
gcloud iam service-accounts create pkm-run --display-name="pkm app and job"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$RUN_SA --role=roles/secretmanager.secretAccessor
```

## 3. Neon

At [neon.com](https://neon.com), create a project: Postgres 17, region **AWS US West 2
(Oregon)**. Copy the **direct** connection string (host without `-pooler`) and
`export NEON_URL='postgresql://…'`. The pooled one runs PgBouncer in transaction mode,
which doesn't suit the app's driver.

A new, empty database needs nothing else: the container runs `alembic upgrade head`
on start. To bring existing data along, see
[Appendix: moving an existing database](#appendix-moving-an-existing-database).

## 4. Secrets

**`SECRET_ENCRYPTION_KEY` encrypts the stored Plaid tokens.** For a fresh database,
generate one (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
For a moved database, it must be the exact key the old host used: any other key makes
every bank need re-linking. Keep a copy somewhere outside Google Cloud too, because a
backup can't be used without it. Pick a long `APP_PASSWORD`.

```bash
printf '%s' "$NEON_URL"            | gcloud secrets create pkm-database-url    --data-file=-
printf '%s' 'FERNET-KEY'           | gcloud secrets create pkm-encryption-key  --data-file=-
printf '%s' 'NEW-LONG-PASSPHRASE'  | gcloud secrets create pkm-app-password    --data-file=-
printf '%s' 'PLAID_CLIENT_ID'      | gcloud secrets create pkm-plaid-client-id --data-file=-
printf '%s' 'PLAID_PRODUCTION_KEY' | gcloud secrets create pkm-plaid-secret    --data-file=-
export SECRETS=DATABASE_URL=pkm-database-url:latest,SECRET_ENCRYPTION_KEY=pkm-encryption-key:latest,APP_PASSWORD=pkm-app-password:latest,PLAID_CLIENT_ID=pkm-plaid-client-id:latest,PLAID_SECRET=pkm-plaid-secret:latest
```

## 5. Build the image in Cloud Build

```bash
gcloud builds submit --tag $IMAGE .
```

This builds on Google's x86 machines. A `docker build` on an Apple Silicon Mac
produces an ARM image, which Cloud Run won't run. `.gcloudignore` keeps `.env` files,
local databases and bank exports out of the upload.

## 6. Sign-in screen and OAuth client (one time, in the console)

A personal Google account has no organization, so Google's built-in IAP sign-in
isn't available. Without your own OAuth client, opening the app shows "Empty Google
Account OAuth client ID(s)/secret(s)".

1. **Consent screen** (Google Auth Platform / OAuth consent screen): app name `pkm`
   and your email; user type **External**; leave it in **Testing**; add your account
   under **Test users**.
2. **OAuth client** (APIs & Services → Credentials → Create credentials → OAuth
   client ID): type **Web application**. Copy the client ID, add this authorized
   redirect URI, then save and copy the client secret:
   `https://iap.googleapis.com/v1/oauth/clientIds/CLIENT_ID:handleRedirect`. Replace
   `CLIENT_ID` with the **whole** client ID, including `.apps.googleusercontent.com`.
   Leaving the placeholder in gives Google's "redirect_uri_mismatch" error.

The client gets attached to IAP right after the deploy in step 7.

## 7. Deploy the app behind Google sign-in

```bash
gcloud run deploy $SERVICE --image $IMAGE --region $REGION \
  --service-account $RUN_SA \
  --no-allow-unauthenticated --iap \
  --max-instances 1 --memory 512Mi \
  --set-secrets "$SECRETS" \
  --env-vars-file deploy/cloudrun/env.yaml

PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud run services add-iam-policy-binding $SERVICE --region $REGION \
  --member=serviceAccount:service-$PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com \
  --role=roles/run.invoker
gcloud iap web add-iam-policy-binding --member=user:$YOU \
  --role=roles/iap.httpsResourceAccessor \
  --region=$REGION --resource-type=cloud-run --service=$SERVICE

# Attach the OAuth client from step 6. The file holds the client secret, so it
# lives in /tmp and is deleted straight after.
cat > /tmp/iap-oauth.yaml <<'EOF'
accessSettings:
  oauthSettings:
    clientId: PASTE_CLIENT_ID
    clientSecret: PASTE_CLIENT_SECRET
EOF
gcloud iap settings set /tmp/iap-oauth.yaml \
  --project=$PROJECT_ID --resource-type=cloud-run --region=$REGION --service=$SERVICE
rm /tmp/iap-oauth.yaml

gcloud run services describe $SERVICE --region $REGION --format='value(status.url)'
```

`--max-instances 1` matters: the container runs `alembic upgrade head` on start, and
two instances must never race it. Open the printed URL. You should get a Google
sign-in, then the app's own password screen.

## 8. Point Plaid at the new URL

Plaid OAuth banks redirect back to `PLAID_REDIRECT_URI`, which must match the
dashboard entry exactly.
1. In the Plaid dashboard (**Team Settings → API → Allowed redirect URIs**), add the
   service URL's site root (`https://…run.app/`). The app forwards an OAuth return
   that lands there to the Accounts page, which finishes the link.
2. Set the same value as `PLAID_REDIRECT_URI` in `deploy/cloudrun/env.yaml`.
3. Apply it:

```bash
gcloud run services update $SERVICE --region $REGION --env-vars-file deploy/cloudrun/env.yaml
```

The redirect only bounces your own browser, which is already signed in, so IAP in
front of the URL doesn't get in its way.

## 9. Daily sync and backups

```bash
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access
printf '{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}' > /tmp/lifecycle.json
gcloud storage buckets update gs://$BUCKET --lifecycle-file=/tmp/lifecycle.json   # keep 30 days
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=serviceAccount:$RUN_SA --role=roles/storage.objectAdmin

gcloud run jobs create $JOB --image $IMAGE --region $REGION \
  --service-account $RUN_SA \
  --command /srv/deploy/cloudrun/job.sh \
  --set-secrets "$SECRETS" \
  --env-vars-file deploy/cloudrun/env.yaml \
  --add-volume name=backups,type=cloud-storage,bucket=$BUCKET \
  --add-volume-mount volume=backups,mount-path=/backups \
  --max-retries 1 --task-timeout 15m --memory 512Mi

gcloud run jobs execute $JOB --region $REGION --wait     # try it once now
gcloud storage ls gs://$BUCKET                            # a pkm-YYYY-MM-DD.sql.gz should appear
```

Then schedule it daily at 6 am Pacific:

```bash
gcloud iam service-accounts create pkm-scheduler
gcloud run jobs add-iam-policy-binding $JOB --region $REGION \
  --member=serviceAccount:pkm-scheduler@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/run.invoker
gcloud scheduler jobs create http $JOB --location $REGION \
  --schedule="0 6 * * *" --time-zone="America/Vancouver" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB}:run" \
  --http-method=POST \
  --oauth-service-account-email=pkm-scheduler@$PROJECT_ID.iam.gserviceaccount.com
```

Two gotchas here, both hit on the first real setup:
- **Keep the braces in `${JOB}:run`.** In zsh (macOS's shell), `$JOB:run` is read as
  `$JOB` plus a `:r` modifier, so the URL silently becomes `…/jobs/pkm-dailyun`. The
  schedule then fails every day with a 404.
- **`NOT_FOUND` on `scheduler jobs create`** right after creating `pkm-scheduler`
  means the new service account hasn't propagated yet. Wait a minute and re-run it.

Check it end to end with `gcloud scheduler jobs run $JOB --location $REGION`, then
look for a new execution in `gcloud run jobs executions list --job $JOB --region $REGION`.

The job backs up first, then syncs, so neither a failed nor a hung Plaid call can
cost a day's backup; either failure marks the run failed. To get an email when that happens, create an alert policy in **Monitoring →
Alerting** on the Cloud Run job's failed executions.

## 10. Check it

On the service URL, on your phone too: sign in, press **Sync now**, and check that
Accounts, Investments and Net Worth look right.

## Day to day

**Deploying a code change:** commit, then

```bash
deploy/cloudrun/deploy.sh
```

The script refuses uncommitted changes (`--dirty` overrides) and runs the backend
tests. Then it builds in Cloud Build, deploys the app and points the daily job at
the same image. Images are tagged with the commit hash, so the revision list shows
exactly what's live.

**Rolling back:** list revisions, then send all traffic to the previous good one:

```bash
gcloud run revisions list --service $SERVICE --region $REGION
gcloud run services update-traffic $SERVICE --region $REGION --to-revisions=REVISION_NAME=100
```

A rollback doesn't undo a migration. The pinned traffic stays in place until the
next `deploy.sh`, which routes traffic back to the latest revision.

New migrations run when the service starts. Test them against a Neon **branch** first:
branch the database in the Neon console, then run
`docker run --rm -e DATABASE_URL='<branch url>' -e SECRET_ENCRYPTION_KEY=x pkm-local alembic upgrade head`.

**Restoring a backup.** Restore into a new, **empty** database, never over live data
and never into a Neon branch: a branch is a copy of the live data, so the dump's
`CREATE TABLE`s fail on tables that already exist. In the Neon console create a new
database (or a new project), copy its **direct** connection string, then:

```bash
export TARGET_URL='postgresql://…'   # plain postgresql://, not the app's +psycopg form
gcloud storage cp gs://$BUCKET/pkm-2026-10-04.sql.gz .
gunzip -c pkm-2026-10-04.sql.gz \
  | docker run --rm -i pkm-local psql -v ON_ERROR_STOP=1 --single-transaction "$TARGET_URL"
docker run --rm pkm-local psql "$TARGET_URL" -c \
  "select (select count(*) from transactions) as txns, (select count(*) from balance_snapshots) as snapshots, (select max(date) from balance_snapshots) as last_snapshot"
```

`ON_ERROR_STOP` and `--single-transaction` make a failed restore fail loudly and
leave nothing behind, instead of exiting 0 halfway through. Compare the counts with
the live app. To switch over, point the `pkm-database-url` secret at the new
database and redeploy. The Plaid tokens in the dump only decrypt with the same
`SECRET_ENCRYPTION_KEY`. Balance snapshots can't be re-fetched from Plaid, so
practise this once before you need it.

**Logs:** Cloud Run → `pkm` (requests) or `pkm-daily` (job runs) → **Logs**.

## Appendix: moving an existing database

This is how the data moved off Replit in October 2026, and works from any Postgres
host. The image carries `pg_dump`/`pg_restore` new enough for both ends, so no local
Postgres tools are needed:

```bash
docker build -t pkm-local .
export OLD_URL='postgresql://…'   # the old host's production database
docker run --rm -v "$PWD":/work pkm-local \
  pg_dump --no-owner --no-privileges -Fc -f /work/move.dump "$OLD_URL"
docker run --rm -v "$PWD":/work pkm-local \
  pg_restore --no-owner --no-privileges -d "$NEON_URL" /work/move.dump
docker run --rm -e DATABASE_URL="$NEON_URL" -e SECRET_ENCRYPTION_KEY=x pkm-local alembic current
```

The last command prints the database's revision. If it isn't `(head)`, run the same
command with `alembic upgrade head`. Use the old host's `SECRET_ENCRYPTION_KEY` in
step 4. `move.dump` holds every transaction and the encrypted Plaid tokens. Git
ignores `*.dump`, but delete the file once the move is done, and keep the old
database for a week as a fallback.
