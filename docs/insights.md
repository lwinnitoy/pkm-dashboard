# Insights (learning, news and progress cards)

The Goals and Budgets pages end with a panel of reading material: what a
retirement target should be, how CPP and OAS fit in, common budget splits, a plan
for co-op work and study terms. That text is **data, not JSX**. It lives in the
`insights` table, and the frontend's `InsightsPanel` only knows how to lay cards
out. So changing what a page says never needs a UI change, and a generator can
publish to a page later without anyone touching the frontend.

- **Backend:** `app/insights/` (`store.py` for read/write/seed sync, `content/*.yaml` for the shipped cards), `app/routers/insights.py` (`/api/insights`)
- **Frontend:** `components/InsightsPanel.tsx`, `lib/markdown.tsx`
- **Tests:** `tests/test_insights.py`, which also validates the shipped YAML

## Card shape

| Field | Meaning |
|---|---|
| `key` | Stable identity, `<page>.<slug>` (e.g. `goals.savings-rate`). Writing the same key again replaces the card. |
| `page` | Which page shows it: `goals`, `budgets`, or any new page that mounts a panel. |
| `kind` | `progress`, `news` or `learn`. The panel shows them in that order, grouped. Unknown kinds still render under their own heading. |
| `title`, `summary` | Always visible. The summary is the takeaway in one sentence. |
| `body` | Shown on "Read more". A small Markdown subset: paragraphs, `- ` bullets, `**bold**`. Anything else renders as literal text, never as HTML. |
| `sources` | `[{title, url}]`, listed under the body. |
| `position` | Sort order within the page (lower first). |
| `origin` | `seed` (owned by the YAML files), `ai`, or `manual`. `ai` cards get an "AI-written" tag in the UI. |
| `model` | Which model wrote an `ai` card; shown in its tag. |
| `expires_at` | Optional. Expired cards are hidden but not deleted, which suits news. |

## Editing the shipped content

Each page's cards are a YAML list in `backend/app/insights/content/<page>.yaml`.
The file name is the page, and every key must start with `<page>.`:

```yaml
- key: budgets.fifty-thirty-twenty
  kind: learn
  position: 10
  title: The 50/30/20 rule
  summary: Split after-tax income into needs, wants and savings.
  body: |
    A paragraph.

    - A bullet
    - **Bold** works; links, headings and HTML don't
  sources:
    - title: Financial Consumer Agency of Canada — Making a budget
      url: https://www.canada.ca/...
```

On every boot the backend syncs these files into the table (`_seed_insights` in
`app/main.py`): new cards are added, changed ones rewritten, and cards deleted
from a file are deleted from the table. So the workflow is: edit the file, run
`pytest tests/test_insights.py` (which catches a bad edit), and redeploy. The sync
is best-effort at boot, so a broken file is logged and skipped rather than
taking the app down. That's why the test is the real gate.

## Publishing from a job or pipeline

This is the hook for the planned generator: a scheduled job, or a DAG running
somewhere else, that has a model write news, progress notes on a goal, or
refreshed explainers.

Over HTTP, with the same bearer token the UI uses (`POST /api/auth/login`):

```bash
curl -X PUT "$APP/api/insights/goals.progress" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "page": "goals",
    "kind": "progress",
    "title": "Retirement goal: 4.2% of the way there",
    "summary": "At $250/month you reach the target about 3 years late; $310/month closes it.",
    "body": "Your TFSA grew **$1,666** above cost basis this year...",
    "sources": [{"title": "FP Canada Projection Assumption Guidelines", "url": "https://www.fpcanada.ca/..."}],
    "origin": "ai",
    "model": "claude-sonnet-5-5",
    "expires_at": "2026-11-01T00:00:00Z"
  }'
```

In process, for example as a step in `app/jobs.py`:

```python
from app.database import SessionLocal
from app.insights import store
from app.schemas import InsightContent

with SessionLocal() as db:
    store.upsert_insight(
        db, "goals.progress", "goals",
        InsightContent(kind="progress", title="...", summary="...", body="..."),
        origin="ai", model="claude-sonnet-5-5",
    )
    db.commit()
```

Conventions that keep a recurring writer well-behaved:

- **Reuse keys for things that are replaced** (`goals.progress`,
  `budgets.this-month`), so each run updates its card instead of piling up new
  ones. Use dated keys only for things that accumulate
  (`goals.news-2026-10-01-cpp-increase`), and give them an `expires_at`.
- **Writing to a seed card's key takes it over.** From then on the boot sync
  leaves it alone. That's how a job can refresh a `learn` card with next year's
  limits. To hand the key back to the file, `DELETE` the row and restart.
- `origin: "seed"` is rejected over the API, because seed rows belong to the YAML
  sync, which would overwrite them. `DELETE` on a seed card returns 409 for the
  same reason: it would come back on the next boot.

## Guardrails for generated content

- The renderer only supports the subset above and never injects HTML, so a model
  can't produce markup, scripts or tracking pixels. Keep it that way. Don't swap
  in a full Markdown renderer with raw-HTML support.
- Cite sources, and prefer primary ones (CRA, Service Canada, FP Canada, FCAC).
  Figures such as contribution limits and CPP/OAS amounts change every year, so a
  `learn` card that quotes them needs a yearly refresh. The generator is the
  natural place to do that.
- The panel labels `ai` cards and ends with a "general information, not
  personalized financial advice" line. A progress card that does use the owner's
  numbers should state its assumptions (return, inflation, contribution).
- A generator that runs off-box (a DAG elsewhere) needs both the app's bearer
  token and model API credentials. Keep them in that platform's secret store, the
  way `SECRET_ENCRYPTION_KEY` and the Plaid keys are kept in Replit Secrets.

## Adding the panel to another page

Mount `<InsightsPanel page="<page>" title="…" />` on the page and add
`content/<page>.yaml`. If a page has no cards, the panel renders nothing.
