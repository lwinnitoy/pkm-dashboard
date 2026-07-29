import { useCallback, useEffect, useState } from "react";
import { api, type Account, type Summary, type Transaction } from "../api/client";
import PlaidLinkButton from "../components/PlaidLinkButton";
import SpendingSummary from "../components/SpendingSummary";
import TransactionsTable from "../components/TransactionsTable";

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, t, a] = await Promise.all([
        api.summary(30),
        api.transactions(50),
        api.accounts(),
      ]);
      setSummary(s);
      setTransactions(t);
      setAccounts(a);
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

      {summary && <SpendingSummary summary={summary} />}

      <section className="card">
        <h2>Recent transactions</h2>
        <TransactionsTable transactions={transactions} />
      </section>
    </div>
  );
}
