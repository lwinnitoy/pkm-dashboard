# Hosting decision (researched 2026-10-03)

**Chosen:** Cloud Run (app + daily job) with IAP sign-in, Neon Postgres, Cloud
Storage backups. It costs about $0/month inside the free tiers. Setup steps are in
[deploy-cloud-run.md](deploy-cloud-run.md).

## Why this shape

- **Plaid needs open egress and a stable HTTPS URL.** A Cloud Run Job triggered by
  Cloud Scheduler has unrestricted egress, and Cloud Scheduler gives 3 jobs free
  [1]. A `*.run.app` URL is a valid Plaid redirect URI.
- **Phone access with real sign-in, nothing to run.** IAP sits directly on a Cloud
  Run service, with no load balancer (GA 2026-03-13) [2][3]. Google sign-in works
  on a phone, and `APP_PASSWORD` stays as a second lock.
- **Free at one user's scale.** Cloud Run's always-free tier (180k vCPU-s, 360k
  GiB-s, 2M requests) covers it. Google still requires a billing account [4].
- **Neon over the alternatives.** Neon Free gives 1 GB and 100 CU-h per project,
  scales to zero after 5 minutes, and keeps 6 hours of point-in-time restore [5].
  Supabase Free pauses after a week of inactivity and has no backups [6].
- **Scale-to-zero means no in-process scheduler.** The daily job
  (`deploy/cloudrun/job.sh`) does the backup, sync and snapshot instead.

## Considered and rejected

| Option | Why not |
|---|---|
| Databricks Free Edition (Lakebase + Apps) | Outbound access is limited to an unpublished list of trusted domains, so reaching Plaid was unverified. Apps stop after 24 h [7] |
| Paid Databricks Apps / Snowflake containers | About $100–275/month to stay on 24/7 |
| Render | Free web services spin down after 15 min, and free Postgres expires after 30 days [8] |
| Fly.io | No free tier for new orgs; managed Postgres from $38/month [9] |
| Tailscale + an always-on box | Workable and simple (the compose setup in [hosting.md](hosting.md)), but every device needs the Tailscale client, and backups and uptime are on you |

## Plaid redirect and webhook rules

- Outside Sandbox, redirect URIs **must be HTTPS**, with no query parameters and no
  `#` routing [10].
- Wildcards aren't allowed on Public Suffix List domains, and `*.run.app` is one, so
  register the exact URI [10].
- An access-protected redirect URL works in practice: Plaid only redirects the
  browser, which already holds the IAP session.
- Webhooks need a publicly reachable URL that Plaid's IPs can call [11]. IAP blocks
  that, so sync stays scheduled. Webhooks would need a separate unauthenticated
  service.

## Backups

`balance_snapshots` can't be re-fetched from Plaid, and Neon Free keeps only 6 hours
of point-in-time restore. Hence the daily `pg_dump` to Cloud Storage, kept for 30
days.

## Sources
1. https://cloud.google.com/scheduler/pricing
2. https://docs.cloud.google.com/run/docs/release-notes
3. https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run
4. https://docs.cloud.google.com/free/docs/free-cloud-features
5. https://neon.com/pricing
6. https://supabase.com/pricing
7. https://docs.databricks.com/aws/en/getting-started/free-edition-limitations
8. https://render.com/docs/free
9. https://docs.fly.io/about/pricing
10. https://plaid.com/docs/link/oauth/
11. https://plaid.com/docs/api/webhooks/
