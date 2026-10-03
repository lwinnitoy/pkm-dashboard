"""Insights: reading material shown on a page (Goals, Budgets, ...).

Cards are rows, not JSX, so what a page says can change without a UI change. Two
kinds of writer share one table:

- **Seed content** ships as YAML in `content/<page>.yaml` and is synced into the
  table on every boot (`store.sync_seed`) — edit the file, redeploy, done.
- **Everything else** — a scheduled AI job, a DAG running elsewhere, a one-off
  script — upserts by key, in-process via `store.upsert_insight` or over HTTP via
  `PUT /api/insights/{key}`. The seed sync never touches those rows.

See docs/insights.md.
"""
