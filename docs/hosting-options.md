# Hosting and data-platform options (researched 2026-10-03)

**Bottom line:** Lakebase **is** in Databricks Free Edition (one project, scale-to-zero) [1]. Free Edition egress is officially limited to "a limited set of trusted domains", and Databricks does not publish that list [1][2]. Whether `production.plaid.com` is reachable is **unverified**: test it before you build anything that depends on it. Databricks Apps on Free Edition run but **stop automatically after 24 h** [1]. Paid Databricks Apps and Snowflake container hosting cost far too much for a 24/7 personal app. The robust free design keeps Plaid calls and web serving off Databricks, and uses Databricks for the analytics layer the roadmap already plans.

## Comparison

| Option | OLTP DB | Scheduled job + egress to Plaid | App hosting + auth (phone) | Free? | Est. $/mo | DE learning |
|---|---|---|---|---|---|---|
| **Databricks Free Edition (all-in)** | Lakebase, 1 project [1]. Native PG passwords (off by default) or 1-h OAuth tokens [4] | Lakeflow Jobs (≤5 concurrent tasks) [1]. Egress **restricted, list unpublished** [1][2] | Apps, ≤3, **auto-stop after 24 h** [1]. Databricks OAuth in front of every request [5]. Login via Google, Microsoft or email OTP [1] | Yes. Non-commercial use only; inactive accounts may be deleted; no SLA [1] | $0 | Very high |
| **Databricks paid (14-day trial → pay-as-you-go)** | Lakebase, ~$0.11/CU-h + ~$0.35/GB-mo (indicative, secondary sources [7]) | Serverless jobs ~$0.35/DBU [7]. Egress open unless you add network policies [6] | Apps Medium = 0.5 DBU/h [8] × ~$0.75/DBU [7] ≈ **$270/mo if always on** | Trial: up to $400 credits for 14 days [9] | ~$275 always-on; ~$5 if the app only runs on demand | Very high |
| **Snowflake** | Snowflake Postgres (GA 2026-02-24 [10]). BURST_XS = 0.0068 credits/h [11] ≈ $10–17/mo | Tasks + External Access Integration. **EAI is not available on trial accounts** [12]. The trial page says EAI is "limited to 10 credits daily until you add payment" [13] | SPCS public endpoint behind Snowflake login [14]. CPU_X64_XS = 0.06 credits/h [11] ≈ 44 credits ≈ $90–130/mo always on | **No free tier.** 30 days, $400 credits [13] | ~$100–150 | High, but different stack |
| **GCP: Cloud Run + IAP + Cloud Scheduler** (DB = Neon or Lakebase) | External | Cloud Run Job triggered by Cloud Scheduler. Unrestricted egress. 3 scheduler jobs free [15] | Cloud Run service with **IAP directly on the service, GA 2026-03-13, no load balancer** [16][17]. Google sign-in works on a phone | Always-free tier: 180k vCPU-s, 360k GiB-s, 2M requests [18]. Billing account required | ~$0–1 | Medium (IaC, IAM, containers) |
| **Neon Free** (DB only) | Postgres. 1 GB/project, 100 CU-h/project, scale-to-zero after 5 min, 6 h PITR [19] | — | — | Yes | $0 (Launch plan: $0.106/CU-h) | Same engine as Lakebase |
| **Supabase Free** (DB only) | 500 MB. **Pauses after 1 week inactive**. No backups [20] | — | — | Yes | $0 (Pro $25) | Low |
| **Prefect Cloud Hobby** (orchestration) | — | 500 min/mo serverless runs, 5 deployments [21]. Egress from fixed IPs [22] | — | Yes | $0 | High (flows, retries, observability) |
| **MotherDuck Lite** (analytics) | — | — | — | 10 GB, 10 h compute [23] | $0 | Medium |
| **Tailscale + always-on box** | Postgres in Docker Compose (repo already has it) | In-process APScheduler. Unrestricted egress | Tailnet only, with HTTPS `*.ts.net` certs from Let's Encrypt [24]. Personal plan: 6 users, free [25] | GCP e2-micro is always-free [18] (tight on 1 GB RAM) | $0 | Low–medium |

Excluded after checking: **Render** (free web services spin down after 15 min, and free Postgres expires after 30 days [26]); **Fly.io** (no free tier for new orgs, Managed PG from $38/mo [27]); **Dagster+** (30-day trial, then $10/mo Solo [28]); **BigQuery sandbox** (tables expire after 60 days, and DML is unsupported [29]). Microsoft Fabric and Astronomer were not verified.

## Recommendation (ranked)

### 1. Serve and ingest on GCP; Databricks Free Edition as the lakehouse (~$0/mo)
- **App:** build the existing single-port image with `gcloud run deploy --source .` from your laptop (no GitHub Actions) and enable IAP on the service, restricted to your Google account. The phone gets a Google login in front of a stable HTTPS `*.run.app` URL. Keep `APP_PASSWORD` as a second factor.
- **Job:** a Cloud Run Job runs `python -m app.jobs` daily from Cloud Scheduler. Secrets live in Secret Manager. Plaid egress is unrestricted.
- **DB:** **Neon Free** is the safer system of record. Lakebase in Free Edition works if you accept the account-deletion and fair-use risks. To use it from outside Databricks, enable native Postgres passwords [4].
- **Data engineering:** a Databricks Free Edition Lakeflow job lands `transactions` and `balance_snapshots` as Delta bronze/silver/gold tables, with a Databricks SQL dashboard on top. This matches the first step in `docs/roadmap.md`. **Caveat:** that job must reach the database. If the DB is Lakebase, the job stays inside Databricks. If it is Neon, egress to `*.neon.tech` is unverified. An alternative is to have the Cloud Run job push Parquet into a Unity Catalog volume or table.
- **Why first:** no restricted-egress dependency on the money path, real SSO, free, and it still teaches Delta, Lakeflow, Unity Catalog and Databricks SQL.

### 2. All-in Databricks Free Edition (Lakebase + Jobs + Apps), only if the egress test passes
- Run `requests.get("https://production.plaid.com")` in a Free Edition serverless notebook, and also from a deployed App, because the App backend calls Plaid for `create-link-token` and `exchange-token`.
- A third-party GitHub issue reports blocked DNS on 2026-09-30 and open egress on 2026-10-02 [3]. The official doc, updated 2026-09-29, still says restricted. The docs say LinkedIn identity verification unlocks only serverless GPU, not egress [1]. Treat egress as **in flux**.
- The 24-hour App auto-stop needs a daily restart. One option is a scheduled job calling the workspace Apps API, which is untested and may conflict with fair use. Apps accept only Databricks-OAuth traffic [5], so Plaid webhooks cannot reach it.
- Highest learning value and $0, but the most fragile.

### 3. Always-on box on your tailnet (Tailscale + Docker Compose on a GCP e2-micro or a home machine)
- Simplest operationally: the in-process scheduler works and nothing is public.
- Plaid redirect URI `https://box.<tailnet>.ts.net/...` is valid HTTPS. Plaid only redirects the browser, so the phone just needs to be on the tailnet (inference; not stated by Plaid).
- Least data-engineering value. You can add Databricks later via option 1's push pattern.

**Avoid for now:** paid Databricks Apps or Snowflake SPCS as a 24/7 host (~$100–275/mo), and Snowflake overall during its trial, since EAI is blocked or limited there.

## Phone access and security

- **Platform-native auth** (Databricks Apps, Snowflake SPCS, Cloud Run IAP): real SSO, nothing to run yourself. Databricks and Snowflake force their own login, which rules out Plaid webhooks. With IAP you can deploy a separate unauthenticated `/webhook` service if you need one.
- **Tailscale:** smallest attack surface, but every device must run the client. Webhooks need Funnel. Machine names appear in Certificate Transparency logs [24].
- **Cloudflare Access + Tunnel** in front of any host: free for up to 50 users [30]. It needs a domain on Cloudflare. Bypass the policy only for the webhook path, and verify Plaid's signed JWT there.
- **Plaid rules:**
  - Redirect URIs **must be HTTPS** outside Sandbox.
  - No query params and no `#` routing.
  - Wildcards are not allowed on Public Suffix List domains [31]. `*.run.app`, `ts.net`, `aws.databricksapps.com`, `onrender.com`, `fly.dev` and `replit.app` are all on the PSL, so register the exact full URI.
  - On web, Link falls back to a pop-up when no redirect URI is set [31].
  - Webhooks need a publicly reachable URL with a valid certificate, called from Plaid's published IPs [32].
- An access-protected redirect URL (IAP, Cloudflare Access, tailnet) should work, because the browser already holds the session cookie. Plaid does not document this case.

## Caveats

- Databricks $/DBU and Lakebase rates come from secondary sources [7]; the official pricing pages render client-side and I could not read them. Lakebase compute was listed at $0.0092/CU-h in some preview-era sources; I assumed ~$0.11 (matching Neon's $0.106).
- Snowflake dollar figures assume $2–3.50/credit, depending on edition and region (AWS Canada Central: $2.25 Standard / $3.50 Enterprise) [11]. I did not confirm that Snowflake Postgres is available on trial accounts.
- **Backups:** `balance_snapshots` cannot be re-fetched from Plaid. Neon Free keeps 6 h of PITR. Free Edition can delete inactive accounts. Schedule a `pg_dump` to cloud storage whichever DB you pick.
- Free Edition is limited to non-commercial use [1]. A personal finance tool fits, but check before any shared or monetized use.

## Sources
1. https://docs.databricks.com/aws/en/getting-started/free-edition-limitations (updated 2026-09-29)
2. https://community.databricks.com/t5/databricks-free-edition-help/whitelist-for-outbound-network-access/td-p/146591
3. https://github.com/VirtueMe/stavangerparking/issues/121 (anecdotal)
4. https://docs.databricks.com/aws/en/oltp/projects/authentication
5. https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth
6. https://docs.databricks.com/aws/en/dev-tools/databricks-apps/networking
7. https://www.flexera.com/blog/finops/databricks-pricing-guide/
8. https://docs.databricks.com/aws/en/dev-tools/databricks-apps/compute-size
9. https://docs.databricks.com/gcp/en/getting-started/free-trial
10. https://docs.snowflake.com/en/release-notes/2026/other/2026-02-24-snowflake-postgres-ga
11. https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf (effective 2026-10-02)
12. https://docs.snowflake.com/en/user-guide/admin-trial-account
13. https://www.snowflake.com/en/snowflake-trial/
14. https://docs.snowflake.com/en/developer-guide/snowpark-container-services/tutorials/advanced/tutorial-8-access-public-endpoint-programmatically
15. https://cloud.google.com/scheduler/pricing
16. https://docs.cloud.google.com/run/docs/release-notes
17. https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run
18. https://docs.cloud.google.com/free/docs/free-cloud-features
19. https://neon.com/pricing
20. https://supabase.com/pricing
21. https://www.prefect.io/pricing
22. https://docs.prefect.io/v3/how-to-guides/deployment_infra/managed
23. https://motherduck.com/product/pricing/
24. https://tailscale.com/kb/1153/enabling-https
25. https://tailscale.com/pricing
26. https://render.com/docs/free
27. https://docs.fly.io/about/pricing
28. https://dagster.io/pricing
29. https://docs.cloud.google.com/bigquery/docs/sandbox
30. https://community.cloudflare.com/t/what-happens-if-i-exceed-50-users/479340
31. https://plaid.com/docs/link/oauth/
32. https://plaid.com/docs/api/webhooks/
