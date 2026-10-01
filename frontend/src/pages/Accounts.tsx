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
  const [deleting, setDeleting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function confirmDelete(id: number) {
    setDeleting(id);
    setError(null);
    try {
      await api.deleteAccount(id);
      setPendingDelete(null);
      await refresh();
    } catch (e) {
      setError(`Couldn't delete the account. ${e instanceof Error ? e.message : e}`);
    } finally {
      setDeleting(null);
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
            <div
              className={`account-row${deleting === a.id ? " is-deleting" : ""}`}
              key={a.id}
              aria-busy={deleting === a.id}
            >
              <div>
                <div className="account-name">
                  {a.name ?? "Account"}{" "}
                  {a.source === "csv" && <span className="chip">imported</span>}
                </div>
                <div className="account-meta">{subtitle(a)}</div>
              </div>

              {deleting === a.id ? (
                <div className="topbar-actions" role="status">
                  <span className="spinner" aria-hidden="true" />
                  <span className="muted">Deleting account and its history…</span>
                </div>
              ) : pendingDelete === a.id ? (
                <div className="topbar-actions">
                  <span className="muted">
                    Delete this account and all of its transactions?
                  </span>
                  <button
                    className="btn btn-ghost"
                    onClick={() => setPendingDelete(null)}
                    disabled={deleting !== null}
                  >
                    Cancel
                  </button>
                  <button
                    className="link-danger"
                    onClick={() => confirmDelete(a.id)}
                    disabled={deleting !== null}
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
                    disabled={deleting !== null}
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
