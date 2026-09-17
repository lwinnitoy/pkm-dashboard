# Manual statement imports (CSV/Excel)

Some institutions can't be linked through Plaid — RBC is the live example (see
[the RBC blocker in CLAUDE.md](../CLAUDE.md)). This path lets you export a CSV or
Excel statement from the bank and load it by hand, producing the same
`Transaction` rows a Plaid sync would. Everything downstream — categories,
rules, budgets, spending charts — is source-agnostic and needs no special-casing.

- **Backend:** `app/imports/` (parsing + reconciliation), `app/routers/imports.py` (`/api/imports/*`)
- **Frontend:** `pages/Import.tsx`
- **Tests:** `tests/test_imports.py`

## Flow

```
export CSV from bank
      ↓
POST /api/imports/preview   → parsed, classified, gaps — nothing written
      ↓   (user confirms)
POST /api/imports/commit    → writes new rows + an ImportBatch
      ↓
GET  /api/imports/coverage  → which periods each account has, and what's missing
```

Preview and commit both take the file; nothing is staged server-side between
them. Fingerprints are deterministic, so the counts the preview showed are the
counts the commit produces.

## How accounts work

A CSV account has no Plaid identity, so `accounts.plaid_item_id` and
`plaid_account_id` are nullable and `accounts.source` is `'plaid' | 'csv'`.
`POST /api/imports/accounts` creates one. Transactions carry the same `source`,
plus `import_fingerprint` and `import_batch_id`.

Balance is not derivable from a statement export, so a manual account's
`current_balance` is whatever you set at creation. The daily snapshot job carries
that value forward (it only refreshes *Plaid* balances), so net worth treats a
manual account as flat until you update it.

## Account type decides asset vs. debt

Net worth splits accounts by `Account.type` against `LIABILITY_TYPES = {"credit",
"loan"}`. A credit card created as the default `depository` therefore **adds** its
balance to net worth instead of subtracting it. The Import page asks for the kind
up front (Chequing / Savings / Credit card / Loan) and
`PATCH /api/imports/accounts/{id}` corrects an existing one. Plaid-linked accounts
aren't editable there — the next sync would overwrite the change.

## Categories, transfers, and double counting

Imported rows are never left with a NULL category: `app/imports/categorize.py`
resolves user rule → transfer detection → `"Uncategorized"`, mirroring what the
Plaid path does via `normalize_category`. This matters more than it looks — a
NULL category used to make rows vanish from every spending total (see below).

Importing a credit card **and** the chequing account that pays it double-books
every payment: money-in on the card, money-out of the chequing account, same
dollars. Descriptions matching `_TRANSFER_PATTERNS` (RBC's
`PAYMENT - THANK YOU / PAIEMENT - MERCI`, e-transfers, card payments) are
categorized `Transfers`, which `NON_SPEND_CATEGORIES` excludes from spending,
budgets, merchant totals **and** the trend chart's income line. Preview reports
how many rows this will affect before you commit.

The patterns are deliberately narrow: a false positive silently deletes real
spending from your totals, which is worse than leaving a row uncategorized. A
user's own `CategoryRule` always wins, so a misfire is corrected once and stays
corrected.

> **Careful with `NOT IN` on a nullable column.** `category NOT IN ('Income',
> 'Transfers')` evaluates to UNKNOWN when `category IS NULL`, so those rows are
> dropped from the result rather than counted. That silently reported `$0` spent
> against 352 imported transactions. Spending queries use the NULL-safe
> `IS_SPEND_CATEGORY` helper in `routers/finance.py` — reuse it rather than
> writing the predicate again.

## Reconciling overlap

Statement exports are requested by date range, so re-importing "last 90 days"
each month re-sends rows you already have. Every row gets a
`sha256(account, date, amount, normalized description, ordinal)` fingerprint,
stored in a UNIQUE column.

The **ordinal** is what makes this safe. It counts identical rows *within their
own (date, amount, description) group*:

| Scenario | Result |
|---|---|
| Two $4.50 coffees on the same day | ordinals 0 and 1 → different fingerprints → **both kept** |
| Those same two rows in next month's overlapping export | reproduce ordinals 0 and 1 → **both deduped** |
| Same row, description reformatted (`COFFEE  SHOP` → `coffee shop`) | normalized before hashing → **deduped** |

A naive content hash would collapse the first case; including file position
would break the second.

### Conflicts

A row whose (date, description) matches a stored transaction with a **different
amount** is a `conflict`, not a duplicate — the bank restated something (a tip
adjustment, a pending amount that settled differently). Conflicts are reported,
and skipped unless the request passes `include_conflicts`, so a restatement is
always a deliberate choice.

Conflict detection is deliberately conservative: it only fires when *exactly
one* stored row shares the date and description. With several, there's no way to
distinguish a restated amount from a second genuine purchase at the same
merchant that day, so those rows are treated as new.

## Detecting gaps

Coverage is tracked as statement **periods** (`ImportBatch.period_start/end`),
not as transaction dates — an imported month with no spending is covered, not
missing. `covered_ranges()` unions those periods (plus the span Plaid has been
syncing, if the account is also linked) and `find_gaps()` returns the holes,
including the tail between the newest period and today.

Preview reports `gaps_before` and `gaps_after`, so you can see what a file
*would* leave uncovered before committing it. `GET /api/imports/coverage` is the
standing monitoring view, surfaced on the Import page.

## Adding another bank

Parsing is a column map, not code. Add a `ColumnMap` to `PRESETS` in
`app/imports/parsers.py`:

```python
TANGERINE = ColumnMap(
    label="Tangerine",
    date=("Date",),                      # alternatives — first present wins
    description=("Name", "Memo"),        # joined, for banks that split a memo
    amount=("Amount",),
    date_formats=("%m/%d/%Y",),
    debit_negative=True,                 # flip to Plaid's positive = money out
)
```

Header matching is case- and whitespace-insensitive, preamble lines above the
header row are skipped, and `(1,234.56)` / `$` / thousands separators are all
handled. Banks that use separate columns instead of one signed amount declare
`debit=` / `credit=` rather than `amount=`.

**Sign convention:** the rest of the app follows Plaid, where **positive = money
out**. RBC (and most Canadian exports) write debits negative, hence
`debit_negative=True`. Getting this backwards silently inverts every chart, so
it's the first thing to check against a new preset.
