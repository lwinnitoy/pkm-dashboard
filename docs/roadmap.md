# Roadmap

Planned directions for the platform, with enough reasoning recorded that a
future session can pick them up cold. Nothing here is in progress — see
[statement-imports.md](statement-imports.md) for what shipped most recently.

## Email recap module

**Idea.** A daily or weekly digest of email that actually needs a response,
rather than reading the inbox directly. The same "personal cloud" premise as the
finance module: pull from a source, normalize it, surface what needs attention.

**Why it fits.** The backend layout already supports this — a module is a router
under `app/routers/` plus one `include_router` line, its own tables in
`models.py`, and a scheduled job in the APScheduler slot that runs the daily
balance snapshot today. No architectural change required.

**Open questions before building:**
- **Source of access.** Claude's Gmail connector is convenient interactively, but
  it authenticates *a Claude session*, not the app. A digest that generates on a
  schedule without anyone present needs the app to hold its own Gmail OAuth
  credential. Decide which of these the module is: a Claude-side workflow that
  reads Gmail and writes a summary into the app, or an app-side integration that
  owns its own token (which would reuse `EncryptedString`, as Plaid tokens do).
- **What "needs addressing" means.** Unanswered threads where you're the last
  recipient? Anything with a question mark? A model call per thread? This is the
  whole value of the feature and the part most likely to be wrong on a first
  pass.
- **Privacy scope.** Email bodies are considerably more sensitive than
  transaction rows. Worth deciding up front whether anything beyond derived
  metadata (subject, sender, a one-line summary) is ever persisted.

## Databricks migration

**Intent.** Eventually move the data layer to Databricks. Two drivers: data
volume grows as modules land beyond finance, and it's deliberate practice with a
platform used at work. **Not being started yet** — recorded here so the
architecture stays migration-friendly in the meantime.

**What would actually move.** The app is a FastAPI service over SQLAlchemy with
Alembic migrations, currently SQLite locally and Postgres in the cloud. A
migration is not a lift-and-shift, because Databricks solves a different problem
than an OLTP app database:

- **Transactional writes** — Plaid sync, categorization, budgets, goals — want a
  real OLTP store. Databricks is a poor fit for row-level updates on the request
  path.
- **Analytics** — spending trends, category comparisons, net-worth history — are
  exactly what a lakehouse is good at, and they're the queries that get more
  expensive as history accrues.

So the realistic shape is **both**: keep Postgres as the system of record, land
raw + modeled data in Databricks, and move the read-heavy analytics endpoints
there. The natural first step is publishing `transactions` / `balance_snapshots`
into Delta tables on a schedule (`app/jobs.py` already exists as a standalone
scheduled entrypoint) and pointing one endpoint — `spending-trend` is the
obvious candidate — at Databricks SQL to prove the round trip.

**What's already in our favour:**
- Routers are thin and read through SQLAlchemy, so swapping a query's backing
  store is a per-endpoint change, not a rewrite.
- `DATABASE_URL` + `app/config.py` already abstract the database target.
- [The investments seam](investments-contract.md) is the precedent worth copying:
  one frozen function signature, so the consumer never learns where the data
  lives. Analytics should get the same treatment before the migration, not
  during it.

**Watch out for:** the daily snapshot history can't be re-fetched from Plaid
(Plaid only exposes *current* balance), so `balance_snapshots` is the one table
where a botched migration is unrecoverable. Back it up before touching it.
