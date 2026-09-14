import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Account,
  type CategoryComparison,
  type Goal,
  type GoalInput,
  type MerchantSpend,
  type NetWorthPoint,
  type PortfolioSummary,
  type Summary,
  type Transaction,
  type TrendPoint,
} from "../api/client";
import { FinanceContext, granularityFor } from "./financeContext";

/**
 * Fetches and shares all finance data across routed pages, driven by a single
 * global date range. Investments are optional (may be unlinked) so the portfolio
 * fetch is isolated and never breaks the rest of the dashboard.
 */
export function FinanceProvider({ children }: { children: React.ReactNode }) {
  const [range, setRange] = useState(180);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [merchants, setMerchants] = useState<MerchantSpend[]>([]);
  const [comparison, setComparison] = useState<CategoryComparison[]>([]);
  const [netWorth, setNetWorth] = useState<NetWorthPoint[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [categories, setCategories] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [s, t, a, tr, m, c, nw, g, cats] = await Promise.all([
        api.summary(range),
        api.transactions(100),
        api.accounts(),
        api.spendingTrend(range, granularityFor(range)),
        api.topMerchants(range, 10),
        api.categoryComparison(range),
        api.netWorth(range),
        api.goals(),
        api.categories(),
      ]);
      setSummary(s);
      setTransactions(t);
      setAccounts(a);
      setTrend(tr);
      setMerchants(m);
      setComparison(c);
      setNetWorth(nw);
      setGoals(g);
      setCategories(cats);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }

    // Investments are optional — isolate so an unlinked/empty state never breaks
    // the page.
    try {
      setPortfolio(await api.investmentsPortfolio());
    } catch {
      setPortfolio(null);
    }
  }, [range]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const sync = useCallback(async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const r = await api.sync();
      // Investments live on a separate Plaid product; sync them too (best-effort,
      // so accounts without investments don't surface an error).
      await api.investmentsSync().catch(() => undefined);
      setMessage(`Synced: +${r.added} new, ${r.modified} updated, ${r.removed} removed.`);
      await refresh();
    } catch (e) {
      setMessage(String(e));
    } finally {
      setSyncing(false);
    }
  }, [refresh]);

  const recategorize = useCallback(
    async (id: number, category: string) => {
      await api.recategorize(id, category);
      await refresh(); // a merchant rule can reassign several transactions
    },
    [refresh],
  );

  const createGoal = useCallback(
    async (g: GoalInput) => {
      await api.createGoal(g);
      await refresh();
    },
    [refresh],
  );

  const deleteGoal = useCallback(
    async (id: number) => {
      await api.deleteGoal(id);
      await refresh();
    },
    [refresh],
  );

  return (
    <FinanceContext.Provider
      value={{
        loading,
        error,
        message,
        syncing,
        range,
        setRange,
        summary,
        transactions,
        accounts,
        trend,
        merchants,
        comparison,
        netWorth,
        goals,
        portfolio,
        categories,
        refresh,
        sync,
        recategorize,
        createGoal,
        deleteGoal,
      }}
    >
      {children}
    </FinanceContext.Provider>
  );
}
