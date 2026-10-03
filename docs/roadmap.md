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

## Automatic transaction categorization

**Idea.** Stop hand-categorizing repeat merchants, especially imported RBC rows.
Normalize merchant keys so one correction covers every store and both sources. Use
Plaid's detailed category and its confidence score. Have a small LLM call, cached per
merchant, suggest categories for merchants you haven't seen before. The research,
options and phased plan are in
[auto-categorization.md](auto-categorization.md).

**Why it fits.** Both paths already go through one rule lookup
(`app/categorization.py`), so the fix starts at a single seam. Phase 1 needs no new
dependencies: a key-normalization fix and a corrected Plaid category mapping.

**Watch out for:** changing the match-key function re-keys existing
`category_rules`. Per-store rules can collapse onto one key with different
categories, so the migration needs a conflict policy.

## AI-written insights

**Idea.** A scheduled writer that keeps the Goals and Budgets reading panels
current. It would post progress notes ("at $250/month you reach the target about
3 years late; $310 closes it"), a monthly budget review, short news items when
something relevant changes (new TFSA/RRSP limits, CPP/OAS indexation), and a yearly
refresh of the `learn` cards that quote figures.

**Why it fits.** The seam already exists: cards are rows, and any writer can
publish one by key, over `PUT /api/insights/{key}` or in-process with
`store.upsert_insight` (see [insights.md](insights.md)). The writer can be a step in
`app/jobs.py`, or a DAG that runs elsewhere and only holds the app's bearer token.
That second option fits the Databricks direction below.

**Open questions before building:**
- **Inputs.** Progress notes need the goal projection, net worth and budget status.
  Read them from the existing endpoints so the writer never queries the database
  directly. Decide which numbers are acceptable to send to a model API.
- **Model and cost.** Writing a handful of cards a week is cheap on any current
  Claude model. Check structured output against `InsightWrite` before publishing,
  and use dated keys plus `expires_at` for news so it doesn't pile up.
- **Trust.** The cards are labelled AI-written, but numbers a model writes about
  your own money still need care. One option: compute every figure in code and have
  the model only phrase it.

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
