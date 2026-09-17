import { useState } from "react";
import { api, type Account } from "../api/client";
import PlaidLinkButton from "../components/PlaidLinkButton";
import { Card, EmptyState } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { currency } from "../lib/format";

function subtitle(a: Account): string {
  return [
    a.institution_name,
    a.official_name,
    a.subtype ?? a.type,
    a.mask ? `••${a.mask}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export default function Accounts() {
  const { accounts, refresh, sync, syncing } = useFinance();
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmDelete(id: number) {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(id);
      setPendingDelete(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Linked accounts"
      sub={accounts.length ? `${accounts.length} accounts` : undefined}
      action={
        <div className="topbar-actions">
          <PlaidLinkButton onLinked={refresh} />
          <button className="btn" onClick={sync} disabled={syncing}>
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
      }
    >
      {error && <p className="error">{error}</p>}

      {accounts.length === 0 ? (
        <EmptyState>
          No accounts linked yet. Use “Connect a bank” to link one via Plaid, or import a
          statement for a bank Plaid can’t reach.
        </EmptyState>
      ) : (
        <div>
          {accounts.map((a) => (
            <div className="account-row" key={a.id}>
              <div>
                <div className="account-name">
                  {a.name ?? "Account"}{" "}
                  {a.source === "csv" && <span className="chip">imported</span>}
                </div>
                <div className="account-meta">{subtitle(a)}</div>
              </div>

              {pendingDelete === a.id ? (
                <div className="topbar-actions">
                  <span className="muted">
                    Delete this account and all of its transactions?
                  </span>
                  <button
                    className="btn btn-ghost"
                    onClick={() => setPendingDelete(null)}
                    disabled={busy}
                  >
                    Cancel
                  </button>
                  <button
                    className="link-danger"
                    onClick={() => confirmDelete(a.id)}
                    disabled={busy}
                  >
                    Delete
                  </button>
                </div>
              ) : (
                <div className="topbar-actions">
                  <span>{currency(a.current_balance)}</span>
                  <button
                    className="link-danger"
                    onClick={() => setPendingDelete(a.id)}
                    aria-label={`Remove ${a.name ?? "account"}`}
                  >
                    Remove
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
