import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Account, type Transaction, type TransactionFilters } from "../api/client";
import TransactionsTable from "../components/TransactionsTable";
import { Card, EmptyState } from "../components/ui";
import { useFinance } from "../data/financeContext";

const PAGE_SIZE = 100;
// The API's cap on rows per request; re-reading a longer list is split to fit.
const MAX_LIMIT = 500;
const SEARCH_DELAY_MS = 300;
const UNCATEGORIZED = "Uncategorized";

/** Rows [offset, offset + count) of the filtered list, in as many requests as the cap needs. */
async function fetchRows(
  filters: TransactionFilters,
  offset: number,
  count: number,
): Promise<Transaction[]> {
  const requests: Promise<Transaction[]>[] = [];
  for (let start = offset; start < offset + count; start += MAX_LIMIT) {
    requests.push(api.transactions(Math.min(MAX_LIMIT, offset + count - start), start, filters));
  }
  return (await Promise.all(requests)).flat();
}

/** Name plus mask, since a re-linked institution can leave two same-named accounts. */
function accountLabel(a: Account): string {
  const name = a.name ?? `Account ${a.id}`;
  return a.mask ? `${name} ••${a.mask}` : name;
}

export default function Transactions() {
  const { range, accounts, categories, refresh } = useFinance();

  const [search, setSearch] = useState("");
  const [q, setQ] = useState(""); // `search`, applied once typing pauses
  const [category, setCategory] = useState("");
  const [accountId, setAccountId] = useState("");

  const [rows, setRows] = useState<Transaction[] | null>(null); // null until first loaded
  const [total, setTotal] = useState(0);
  const [anyAtAll, setAnyAtAll] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const filters = useMemo<TransactionFilters>(
    () => ({
      period: range,
      q: q || undefined,
      category: category || undefined,
      account_id: accountId ? Number(accountId) : undefined,
    }),
    [range, q, category, accountId],
  );

  // Each reload starts a new generation. A response from an older one (the
  // filters changed while it was in flight) is dropped rather than shown.
  const generation = useRef(0);

  /** Replace the list with its first `count` rows under the current filters. */
  const reload = useCallback(
    async (count: number) => {
      const gen = ++generation.current;
      setLoading(true);
      setError(null);
      try {
        const [page, matching] = await Promise.all([
          fetchRows(filters, 0, count),
          api.transactionCount(filters),
        ]);
        // Only an empty result needs this, to tell "nothing synced yet" apart
        // from "nothing matches".
        const any = matching.total > 0 || (await api.transactionCount()).total > 0;
        if (gen !== generation.current) return;
        setRows(page);
        setTotal(matching.total);
        setAnyAtAll(any);
      } catch (e) {
        if (gen === generation.current) setError(String(e));
      } finally {
        if (gen === generation.current) setLoading(false);
      }
    },
    [filters],
  );

  useEffect(() => {
    void reload(PAGE_SIZE);
  }, [reload]);

  async function loadMore() {
    if (!rows) return;
    const gen = generation.current;
    setLoadingMore(true);
    try {
      const next = await fetchRows(filters, rows.length, PAGE_SIZE);
      if (gen !== generation.current) return; // a reload owns the list now
      // A sync landing between pages shifts every offset; don't show a row twice.
      setRows((prev) => {
        const shown = new Set((prev ?? []).map((t) => t.id));
        return [...(prev ?? []), ...next.filter((t) => !shown.has(t.id))];
      });
    } catch (e) {
      if (gen === generation.current) setError(String(e));
    } finally {
      setLoadingMore(false);
    }
  }

  async function recategorize(id: number, picked: string) {
    // Re-read as deep as the user has loaded, so the list doesn't snap back to page one.
    const depth = Math.max(rows?.length ?? 0, PAGE_SIZE);
    setRows((prev) => prev && prev.map((t) => (t.id === id ? { ...t, category: picked } : t)));
    try {
      await api.recategorize(id, picked);
    } catch (e) {
      await reload(depth); // undo the optimistic pick
      setError(`Couldn't recategorize: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    // The pick became a merchant rule that can move other rows too, both here
    // and in the other pages' totals, so re-read everything rather than one row.
    await Promise.all([reload(depth), refresh()]);
  }

  function clearFilters() {
    setSearch("");
    setQ("");
    setCategory("");
    setAccountId("");
  }

  // Uncategorized first: working through it is what this filter is mostly for.
  const categoryOptions = [UNCATEGORIZED, ...categories.filter((c) => c !== UNCATEGORIZED)];

  let body: React.ReactNode;
  if (rows === null) {
    body = loading && (
      <div className="loading-row" role="status">
        <span className="spinner" aria-hidden="true" />
        Loading transactions…
      </div>
    );
  } else if (rows.length === 0) {
    body = !anyAtAll ? (
      <EmptyState>
        No transactions yet. Connect a bank and hit “Sync now”, or import a statement.
      </EmptyState>
    ) : q || category || accountId ? (
      <EmptyState>
        No transactions match these filters.{" "}
        <button className="link-plain" onClick={clearFilters}>
          Clear filters
        </button>
      </EmptyState>
    ) : (
      <EmptyState>No transactions in this date range.</EmptyState>
    );
  } else {
    body = (
      <div className={`txn-results${loading ? " is-loading" : ""}`} aria-busy={loading}>
        <TransactionsTable
          transactions={rows}
          categories={categories}
          onRecategorize={recategorize}
        />
        {rows.length < total && (
          <div className="load-more">
            <button className="btn btn-ghost" onClick={loadMore} disabled={loading || loadingMore}>
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <Card
      title="Transactions"
      sub="Click a category to recategorize — it becomes a merchant rule for past and future"
    >
      <div className="filter-bar">
        <input
          type="search"
          placeholder="Search description or merchant"
          aria-label="Search transactions"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Filter by category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">All categories</option>
          {categoryOptions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by account"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {accountLabel(a)}
            </option>
          ))}
        </select>
        {/* Always mounted, so screen readers announce the new count after filtering. */}
        <span className="filter-count" role="status">
          {rows && rows.length > 0
            ? `Showing ${rows.length.toLocaleString("en-US")} of ${total.toLocaleString("en-US")}`
            : ""}
        </span>
      </div>

      {error && <p className="error">{error}</p>}
      {body}
    </Card>
  );
}
