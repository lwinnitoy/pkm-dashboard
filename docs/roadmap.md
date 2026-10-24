# Roadmap

Planned work for Ledger, with enough reasoning recorded that a future session can
pick it up cold. Ledger is a personal-finance app and stays one: these are
improvements to that, not new modules.

## Automatic transaction categorization

**Idea.** Stop hand-categorizing repeat merchants, especially imported RBC rows.
Normalize merchant keys so one correction covers every store and both sources. Use
Plaid's detailed category and its confidence score. Have a small LLM call, cached per
merchant, suggest categories for merchants you haven't seen before. The research,
options and phased plan are in
[auto-categorization.md](auto-categorization.md).

**Done so far.** Synced rows are mapped on Plaid's *detailed* category
(`normalize_category` in `app/plaid_client.py`). Card payments are Transfers,
groceries are Groceries, rent is Housing, and the missing primaries are mapped. That's
item 2 of Phase 1. Storing the detailed category and its confidence is still to do.

**Why it fits.** Both paths already go through one rule lookup
(`app/categorization.py`), so the rest starts at a single seam. The remaining Phase 1
items need no new dependencies.

**Watch out for:** changing the match-key function re-keys existing
`category_rules`. Per-store rules can collapse onto one key with different
categories, so the migration needs a conflict policy.

## AI-written insights

**Idea.** A scheduled writer that keeps the Goals and Budgets reading panels
current. It would post:
- progress notes ("at $250/month you reach the target about 3 years late; $310
  closes it");
- a monthly budget review;
- short news items when something relevant changes (new TFSA/RRSP limits, CPP/OAS
  indexation);
- a yearly refresh of the `learn` cards that quote figures.

**Why it fits.** The seam already exists: cards are rows, and any writer can
publish one by key, over `PUT /api/insights/{key}` or in-process with
`store.upsert_insight` (see [insights.md](insights.md)). The writer can be a step in
`app/jobs.py`, which the daily Cloud Run job already runs.

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
