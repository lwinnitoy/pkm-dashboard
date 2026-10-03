# Automatic transaction categorization

Design research only; nothing is built (2026-09-30). Paths are relative to
`backend/`. See also [statement-imports.md](statement-imports.md) and the Databricks
plan in [roadmap.md](roadmap.md).

## 1. Problem and current state

| Path | Category logic | Code |
|---|---|---|
| Plaid sync | User rule, else PFC `primary` mapped onto the 14 seed categories | `routers/plaid.py::_upsert_transaction`, `plaid_client.py::normalize_category` |
| Import | User rule, else transfer regex, else `Uncategorized` | `imports/categorize.py::resolve_category` |
| Manual edit | Sets the row **and** upserts a `CategoryRule` that rewrites every match | `routers/finance.py::recategorize_transaction`, `categorization.py::upsert_rule_and_apply` |

The app already learns a rule from every correction; the weak point is the **key**.
`match_key()` is just `(merchant_name or name).strip().lower()`, and imported rows
have no `merchant_name`. Running the real function:

| Input | Key today |
|---|---|
| `MCDONALDS #1234 VICTORIA` | `mcdonalds #1234 victoria` |
| `MCDONALDS #5678 SAANICH` | `mcdonalds #5678 saanich` |
| Plaid row, `merchant_name="McDonald's"` | `mcdonald's` |

Three keys, so each correction covers one store in one source. Chequing debit rows
may be worse. RBC prefixes them with a channel phrase and a number
(`C-IDP PURCHASE - 1234` in OFX;
[ofxcat](https://github.com/MusikPolice/ofxcat/blob/master/src/main/java/ca/jonathanfritz/ofxcat/cleaner/RbcTransactionCleaner.java)),
and the parser joins Description 1 and 2. If that number varies, every row gets a
fresh key. Verify against a real export.

Other gaps:
- **The Plaid mapping loses data.** `GROCERIES` isn't a PFC primary (groceries are
  `FOOD_AND_DRINK_GROCERIES`), so synced groceries land in **Dining**.
  `GENERAL_SERVICES`, `GOVERNMENT_AND_NON_PROFIT` and `HOME_IMPROVEMENT` (plus v2's
  `LOAN_DISBURSEMENTS` and `OTHER`) become Uncategorized.
  `LOAN_PAYMENTS_CREDIT_CARD_PAYMENT` becomes **Loans** and counts as spending, the
  double-booking the import path avoids. `detailed` and `confidence_level` are thrown
  away.
- **No exceptions and no provenance.** Every edit becomes a rule that rewrites every
  row with that key. Nothing records who chose a category, and no endpoint lists or
  deletes rules.
- `resolve_category` queries once per row, in preview and again in commit.

## 2. Options

### 2.1 Merchant normalization and better rules

**How.** `merchant_key()` does the following:
- Lowercases the text, drops apostrophes and collapses whitespace.
- Strips bank channel phrases (`Contactless Interac purchase - 5207`).
- Strips processor prefixes (`SQ *`, `TST-`, `PAYPAL *`) but keeps the name after
  them. `AMZN Mktp CA*…` becomes `amazon`.
- Strips one trailing province and one trailing city, but never empties the key.
- Drops store numbers and truncated tails like ` - Victori`.

A 30-line scratch prototype produced:

| Input | Key |
|---|---|
| `MCDONALDS #1234 VICTORIA`, `MCDONALDS #5678 SAANICH`, `McDonald's` | `mcdonalds` |
| `STARBUCKS 04785 VICTORIA`, `SUBWAY 11675 VICTORIA` | `starbucks`, `subway` |
| `TST-Tacofino - Victori Victoria` | `tacofino` |
| `WHISTLE BUOY BREWING VICTORIA`, `SQ *WHISTLE BUOY BREWING Victoria BC` | `whistle buoy brewing` |
| `CITY OF VICTORIA VICTORIA` | `city of victoria` |
| `UBER* EATS`, `UBER* TRIP` | kept apart on purpose |

Store it as an indexed `transactions.merchant_key`, so rules match on equality across
both sources. Then add:
- **Majority voting.** Actual Budget uses the payee's most common category. If no
  category dominates, treat the merchant as ambiguous and only suggest.
- **A seeded keyword file, ranked below user rules.** For example, Thrifty Foods →
  Groceries, Petro-Canada → Transport, `brewing|pub` → Dining.

| | |
|---|---|
| **Effort** | 1–2 days, mostly a migration that backfills `merchant_key` and re-keys `category_rules` (old per-store rules may conflict). |
| **Accuracy** | As good as your labels; coverage is the share of rows from merchants labelled once. |
| **Cost and privacy** | None. |
| **Traps** | Over-merging (Uber, Amazon). Leave `reconcile.normalize_description` alone, because it feeds the import fingerprint. |
| **Databricks** | `merchant_key` gives a clean merchant column across both sources. |

### 2.2 Plaid's enrichment

**PFC on synced rows** is free.
- **Fields:** `detailed` (104 values in v1, 127 in v2) and `confidence_level`
  (`VERY_HIGH` >98%, `HIGH` >90%, `MEDIUM`, `LOW`, `UNKNOWN`;
  [docs](https://plaid.com/docs/api/products/transactions/)).
- **Use:** map on `detailed`, falling back to `primary`. Apply `VERY_HIGH` and `HIGH`
  automatically, and suggest the rest.
- **Taxonomy versions:** v2 shipped 2025-12-03 and is the only version for accounts
  enabled since. Older accounts get v1 unless they pass
  `personal_finance_category_version`, which plaid-python 29.0.0 lacks. Because v2
  is a superset, one v2 map covers both
  ([taxonomy](https://plaid.com/documents/pfc-taxonomy-all.csv)).

**Enrich** (`/transactions/enrich`) is the only way to get Plaid categories for RBC
rows. It covers US/CA, up to 100 transactions per call: description, amount,
direction and currency in; PFC with confidence, merchant and location out. Plaid's
[pricing page](https://plaid.com/pricing/) lists it on every plan, including Pay as
You Go, but bills per transaction at an unpublished price
([Enrich](https://plaid.com/docs/enrich/)). The account already has Production
access, so enabling it may only take a dashboard request. If it's cheap, it could
replace the LLM for RBC rows and keep both sources on one taxonomy. **Databricks:**
detailed category and confidence are useful analytics columns.

### 2.3 Classifier on your own labels

**How.** scikit-learn TF-IDF character n-grams (`char_wb`, 3–5) over key and
description, plus amount bucket, direction and account. Use
`LogisticRegression(class_weight="balanced")` for probabilities; `LinearSVC` needs
calibration, and `ComplementNB` is a baseline.

Train only on confirmed labels, one sample per merchant. Otherwise Starbucks dominates
and the model learns from its own guesses. Training takes under a second, so retrain
in-process instead of storing a pickle.

**Accuracy.** On seen merchants it only repeats 2.1. On unseen ones it has nothing but
shared tokens (`BREWING`, `PIZZA`), so it's weak.
- Evaluate with a time split and with `GroupKFold` by `merchant_key`. A random split
  leaks merchant identity, so it measures memory, not generalization.
- Report per-category precision and coverage at the auto-apply threshold.
- Categories with fewer than 10 labels will do poorly.

**Cost:** $0 and local; adds scikit-learn, numpy and scipy. **Databricks:** not needed
at this size.

### 2.4 Embeddings and nearest neighbour

Label a new merchant from its nearest labelled neighbours in embedding space. Three
problems:
- Anthropic has no embeddings model
  ([it points to Voyage AI](https://platform.claude.com/docs/en/build-with-claude/embeddings)).
  The alternatives are a second vendor with an LLM's privacy exposure, or a local
  model that pulls in PyTorch.
- Generic embeddings know little about brands in short, noisy descriptors.
- Neighbours are still limited to what you've labelled.

There's no clear win. **Databricks:** Vector Search would put the lakehouse in the
write path.

### 2.5 LLM classification

**How.** Send merchant keys with no rule or memory to Claude Haiku 4.5
(`claude-haiku-4-5`, snapshot `claude-haiku-4-5-20251001`), 25–50 per request.
- **Prompt:** your categories with definitions, about 40 examples from your history,
  and "merchants are mostly in Victoria, BC".
- **Output:** structured outputs (`output_config.format`, supported on Haiku 4.5) with
  an `enum` of categories plus `UNKNOWN`, and a coarse `confidence`.
- **Precision:** borrow Maybe's rule to always prefer null over a false positive.
- **Caching:** results go in `merchant_classifications`, keyed by merchant key, model
  and a hash of the category list, so each merchant is classified once.

**Accuracy.** Best for new merchants: it knows Tacofino is tacos and Whistle Buoy is
a brewery. Opaque or ambiguous merchants should come back
`UNKNOWN`. Self-reported confidence is coarse, so calibrate thresholds on your
acceptance rate.

**Cost (estimate; check with `count_tokens`).** Haiku 4.5 costs $1 per million input
tokens and $5 per million output tokens
([pricing](https://platform.claude.com/docs/en/about-claude/pricing)).
- **Assumptions:** a 1,300-token fixed prompt, and 50 merchants per call at about 30
  tokens in and 25 out each.
- **Per call:** about 2,800 tokens in and 1,250 out, roughly $0.009. That's
  **$0.18 per 1,000 merchants**.
- **In practice:** only unseen merchants are sent. A first backfill of 1,000
  transactions is about $0.05–0.10, then cents a month. The Batch API halves it.
- **Batch, don't cache.** One call per transaction costs about $1.50 per 1,000, and the
  fixed prompt is under Haiku 4.5's 4,096-token caching minimum.

**Privacy.**
- **Send:** the key, one raw descriptor, direction, an amount bucket and account type.
- **Never send:** dates, balances or transfer rows (e-transfers carry people's names).
- **Anthropic's terms:** inputs are deleted within 30 days unless flagged
  ([retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)),
  and the commercial terms prohibit training on customer content.
- **Opt-in:** off unless `ANTHROPIC_API_KEY` is set, like `APP_PASSWORD` for auth.
- **Failures:** on API errors, leave rows Uncategorized.

**Databricks:** `ai_classify()` could backfill over Delta, but the results would have
to flow back into Postgres. Keep the live path in the app.

### 2.6 Hybrid pipeline

One `categorize()` module, called from `_upsert_transaction` and from import
preview/commit. It loads rules once per request, and the first match wins:

1. **Your manual choice for the row** (`category_source="manual"`), never
   overwritten. Plaid re-adds posted transactions under a new id, so carry it over
   via `pending_transaction_id`.
2. **Your rules, then transfer detection.** Rules can later add contains, regex,
   amount and account conditions, as in Firefly III.
3. **Merchant memory**, unless the merchant is ambiguous.
4. **Plaid PFC** at `VERY_HIGH` or `HIGH`.
5. **The keyword file.**
6. **LLM or classifier.** A "high" result is applied; anything lower only goes into
   `suggested_category`.
7. **`Uncategorized`.**

**Schema** (nullable, using `batch_alter_table`):
- `transactions`: `merchant_key` (indexed), `category_source`, `category_confidence`,
  `suggested_category`, `plaid_category_detailed`, `plaid_confidence`.
- `category_rules`: `source` (`user` or `learned`) and `updated_at`.
- A new `merchant_classifications` table.

**UI.**
- A suggestion chip with one-click accept, which counts as a manual label.
- On recategorize, ask "this one, or all 23 McDonald's?" instead of silently creating
  a rule.
- A Needs-review view grouped by merchant key and sorted by amount. Group on the
  server: the Transactions page pages through rows, so it never holds them all.
- A source badge (rule, Plaid, AI) and a rules list with delete.

**Databricks:** provenance columns let Delta track automation and correction rates.

### How self-hosted tools do it

| Tool | Approach |
|---|---|
| [Firefly III](https://docs.firefly-iii.org/how-to/firefly-iii/features/rules/) | Trigger/action rules that fire on create or update and can run retroactively. No built-in ML; [community webhooks](https://github.com/bahuma20/firefly-iii-ai-categorize) send rows to OpenAI. |
| [Actual Budget](https://actualbudget.org/docs/budgeting/rules/) | Categorizing creates a payee rule from the payee's most common category; imported payees are first renamed to clean names. |
| [Maybe](https://github.com/maybe-finance/maybe/blob/main/app/models/provider/openai/auto_categorizer.rb) (archived) | Rules, plus OpenAI on uncategorized rows only (≤25 per call, enum + `"null"`). It records source `ai`, then locks the field. |
| [smart_importer](https://github.com/beancount/smart_importer) | A local linear SVC over narration and payee n-grams, retrained on every import. |

All four clean the payee, remember corrections, and let ML or an LLM fill only the
blanks.

## 3. Comparison

| Option | Effort | Repeat merchants | New merchants | Cost | Privacy | Databricks |
|---|---|---|---|---|---|---|
| 2.1 Normalize + rules | S | **Fixes** | Keyword file only | $0 | Local | Merchant dimension |
| 2.2 PFC (synced) | S | n/a | Good, synced only | $0 | Already with Plaid | Detailed category |
| 2.2 Enrich (CSV) | M | n/a | Good | Per transaction, unpublished | RBC rows go to Plaid | None |
| 2.3 Classifier | M | Redundant | Weak | $0 | Local | Not needed |
| 2.4 Embeddings | M | Redundant | Moderate | Vendor or heavy model | Vendor or local | Write-path conflict |
| 2.5 LLM | M | Redundant | **Strong** | ~$0.18 per 1k merchants | Descriptors go to Anthropic | Keep in app |
| 2.6 Hybrid | 2.1 + 2.2 + 2.5 + UI | Yes | Yes | Cents/month | Opt-in | Provenance columns |

## 4. Recommended plan

**Phase 1: cheap fixes with no new dependencies (1–2 days).**
1. Add `merchant_key()` and its column. The migration backfills it and re-keys
   `category_rules`; when rules conflict, the most recent wins and the rest are
   logged. Use the 2.1 table as tests.
2. Map PFC on `detailed`. This fixes Groceries, maps the missing primaries and turns
   card payments into Transfers. Store the detailed category and its confidence.
3. Add the keyword file below user rules.
4. Load rules once per import, and add `GET`/`DELETE /api/finance/rules`.

Phase 1 is done when re-importing an RBC statement categorizes McDonald's at every
store, with the Uncategorized share measured before and after.

**Phase 2: review and LLM suggestions (3–5 days).**
1. Build the provenance columns, the precedence module, a sync guard for manual rows,
   the review view and "apply to all similar".
2. Add suggestions for unseen merchants: Haiku 4.5, or Enrich if its price turns out
   low. Make it opt-in and suggest-only at first.
3. Turn on auto-apply for "high" once about 100 suggestions show at least 95%
   acceptance.
4. Sweep leftovers in `app.jobs`.

**Phase 3: only if the data calls for it.**
- A local classifier, if third-party calls become unacceptable. Adopt it only if it
  beats Phase 2 on a split grouped by merchant.
- Amount rules for merchants like `CITY OF VICTORIA`.
- Skip embeddings.

## 5. Open questions

- After Phase 1, what share of new rows come from already-labelled merchants? That
  sizes Phase 2.
- Is the Plaid account on PFC v1 or v2, and what does Enrich cost per transaction on
  it?
- Should Coffee, Fast food or Alcohol be categories? That changes the PFC map and the
  prompt.
- Should ambiguous merchants (City of Victoria, Amazon, Costco) get amount rules, or
  always go to review?
- Should suggestions count toward budgets before you accept them?
- Is it acceptable to send merchant descriptors and amount buckets to Anthropic?
- What does a real RBC chequing export put in Description 1 and Description 2?

Other sources: [PFC migration](https://plaid.com/docs/transactions/pfc-migration/),
[pending→posted](https://plaid.com/docs/transactions/transactions-data/),
[Enrich API](https://plaid.com/docs/api/products/enrich/),
[structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
[prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching),
[commercial terms](https://www.anthropic.com/legal/commercial-terms),
[`ai_classify`](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_classify).
