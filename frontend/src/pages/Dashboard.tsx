import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Account,
  type CategoryComparison,
  type Goal,
  type GoalInput,
  type MerchantSpend,
  type NetWorthPoint,
  type Summary,
  type Transaction,
  type TrendPoint,
} from "../api/client";
import GoalsCard from "../components/GoalsCard";
import NetWorthChart from "../components/NetWorthChart";
import PlaidLinkButton from "../components/PlaidLinkButton";
import SpendingSummary from "../components/SpendingSummary";
import SpendingTrendChart from "../components/SpendingTrendChart";
import TopMerchants from "../components/TopMerchants";
import TransactionsTable from "../components/TransactionsTable";

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [merchants, setMerchants] = useState<MerchantSpend[]>([]);
  const [comparison, setComparison] = useState<CategoryComparison[]>([]);
  const [netWorth, setNetWorth] = useState<NetWorthPoint[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, t, a, tr, m, c, nw, g] = await Promise.all([
        api.summary(30),
        api.transactions(50),
        api.accounts(),
        api.spendingTrend(180, "month"),
        api.topMerchants(30, 10),
        api.categoryComparison(30),
        api.netWorth(180),
        api.goals(),
      ]);
      setSummary(s);
      setTransactions(t);
      setAccounts(a);
      setTrend(tr);
      setMerchants(m);
      setComparison(c);
      setNetWorth(nw);
      setGoals(g);
    } catch (e) {
      setMessage(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSync = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const r = await api.sync();
      setMessage(`Synced: +${r.added} new, ${r.modified} updated, ${r.removed} removed.`);
      await refresh();
    } catch (e) {
      setMessage(String(e));
    } finally {
      setSyncing(false);
    }
  };

  const handleCreateGoal = async (g: GoalInput) => {
    await api.createGoal(g);
    await refresh();
  };

  const handleDeleteGoal = async (id: number) => {
    await api.deleteGoal(id);
    await refresh();
  };

  return (
    <div className="dashboard">
      <header className="topbar">
        <h1>Finances</h1>
        <div className="actions">
          <PlaidLinkButton onLinked={refresh} />
          <button onClick={handleSync} disabled={syncing}>
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
      </header>

      {message && <div className="banner">{message}</div>}

      {accounts.length > 0 && (
        <div className="accounts">
          {accounts.map((a) => (
            <span key={a.id} className="chip">
              {a.name ?? "Account"}
              {a.current_balance != null && `: $${a.current_balance.toFixed(2)}`}
            </span>
          ))}
        </div>
      )}

      <GoalsCard goals={goals} onCreate={handleCreateGoal} onDelete={handleDeleteGoal} />

      <NetWorthChart data={netWorth} />

      {summary && <SpendingSummary summary={summary} comparison={comparison} />}

      <SpendingTrendChart data={trend} />

      <TopMerchants data={merchants} />

      <section className="card">
        <h2>Recent transactions</h2>
        <TransactionsTable transactions={transactions} />
      </section>
    </div>
  );
}
