import { useState } from "react";
import { api, type Account } from "../api/client";
import PlaidLinkButton from "../components/PlaidLinkButton";
import { Card, EmptyState } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { dayKey } from "../lib/dates";
import { currency, shortDate } from "../lib/format";

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

function isLiability(a: Account): boolean {
  return /credit|loan/i.test(a.type ?? "");
}

/**
 * Inline editor for an imported account's balance. Statement exports carry no
 * balance, so the owner types the one their bank shows; transactions imported
 * later with newer dates roll it forward (app/imports/balance.py).
 */
function BalanceForm({
  account,
  onDone,
}: {
  account: Account;
  onDone: (saved: boolean) => void;
}) {
  const [amount, setAmount] = useState(
    account.current_balance == null ? "" : String(account.current_balance),
  );
  const [asOf, setAsOf] = useState(dayKey());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const balance = Number(amount);
    if (amount.trim() === "" || Number.isNaN(balance)) {
      setError("Enter a number.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateManualAccount(account.id, { balance, balance_as_of: asOf });
      onDone(true);
    } catch (err) {
      setError(`Couldn't save. ${err instanceof Error ? err.message : err}`);
      setSaving(false);
    }
  }

  return (
    <form className="balance-form" onSubmit={save}>
      <label>
        {isLiability(account) ? "Amount owed" : "Balance"}
        <input
          type="number"
          step="0.01"
          inputMode="decimal"
          value={amount}
          autoFocus
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      <label>
        As of
        <input
          type="date"
          value={asOf}
          max={dayKey()}
          onChange={(e) => setAsOf(e.target.value)}
        />
      </label>
      <button type="submit" className="btn" disabled={saving}>
        {saving ? "Saving…" : "Save"}
      </button>
      <button type="button" className="btn btn-ghost" onClick={() => onDone(false)}>
        Cancel
      </button>
      {error && <span className="error">{error}</span>}
    </form>
  );
}

export default function Accounts() {
  const { accounts, loading, refresh, sync, syncing } = useFinance();
  const [editingBalance, setEditingBalance] = useState<number | null>(null);
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

      {loading && accounts.length === 0 ? (
        <EmptyState>Loading accounts…</EmptyState>
      ) : accounts.length === 0 ? (
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
                {a.source === "csv" && a.balance_anchor_date && (
                  <div
                    className="account-note"
                    title="The balance you entered, adjusted by every transaction imported with a later date."
                  >
                    Balance entered for {shortDate(a.balance_anchor_date)}, updated by later imports
                  </div>
                )}
              </div>

              {editingBalance === a.id ? (
                <BalanceForm
                  account={a}
                  onDone={async (saved) => {
                    setEditingBalance(null);
                    if (saved) await refresh();
                  }}
                />
              ) : deleting === a.id ? (
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
                  {a.source === "csv" && a.current_balance == null ? (
                    <button
                      className="btn btn-ghost"
                      onClick={() => setEditingBalance(a.id)}
                      disabled={deleting !== null}
                    >
                      Set balance
                    </button>
                  ) : (
                    <span>{currency(a.current_balance)}</span>
                  )}
                  {a.source === "csv" && a.current_balance != null && (
                    <button
                      className="link-plain"
                      onClick={() => setEditingBalance(a.id)}
                      disabled={deleting !== null}
                      aria-label={`Edit ${a.name ?? "account"} balance`}
                    >
                      Edit
                    </button>
                  )}
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
