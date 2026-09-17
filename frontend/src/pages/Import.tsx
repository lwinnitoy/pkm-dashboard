import { useCallback, useEffect, useState } from "react";
import type {
  AccountCoverage,
  DateRange,
  ImportBatch,
  ImportPreset,
  ImportPreview,
  ImportResult,
  ImportRow,
} from "../api/client";
import { api } from "../api/client";
import { Card, EmptyState } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { currency, longDate } from "../lib/format";

const NEW_ACCOUNT = "new";

/** Plaid's type/subtype vocabulary. `type` decides whether net worth counts the
 *  balance as an asset or a debt, so a credit card must not be "depository". */
const ACCOUNT_KINDS = [
  { key: "chequing", label: "Chequing", type: "depository", subtype: "checking" },
  { key: "savings", label: "Savings", type: "depository", subtype: "savings" },
  { key: "credit", label: "Credit card", type: "credit", subtype: "credit card" },
  { key: "loan", label: "Loan", type: "loan", subtype: null },
] as const;

function rangeLabel(r: DateRange): string {
  return `${longDate(r.start)} – ${longDate(r.end)}`;
}

function GapList({ gaps }: { gaps: DateRange[] }) {
  if (gaps.length === 0) return <span className="badge-ok">No gaps</span>;
  return (
    <ul className="gap-list">
      {gaps.map((g) => (
        <li key={`${g.start}-${g.end}`}>
          <span className="badge-warn">Missing</span> {rangeLabel(g)}
        </li>
      ))}
    </ul>
  );
}

function RowTable({ rows }: { rows: ImportRow[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Description</th>
          <th className="num">Amount</th>
          <th>Category</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.date}-${r.description}-${i}`}>
            <td>{longDate(r.date)}</td>
            <td>{r.description}</td>
            <td className={`num ${r.amount >= 0 ? "amt-out" : "amt-in"}`}>
              {currency(Math.abs(r.amount))}
            </td>
            <td>
              <span className={r.category === "Transfers" ? "tag status-transfer" : "muted"}>
                {r.category}
              </span>
            </td>
            <td>
              <span className={`tag status-${r.status}`}>{r.status}</span>
              {r.existing_amount != null && (
                <span className="muted"> was {currency(Math.abs(r.existing_amount))}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Import() {
  const { accounts, refresh } = useFinance();
  const [presets, setPresets] = useState<ImportPreset[]>([]);
  const [preset, setPreset] = useState("rbc");
  const [accountChoice, setAccountChoice] = useState<string | null>(null);
  const [newAccountName, setNewAccountName] = useState("RBC Chequing");
  const [newAccountKind, setNewAccountKind] = useState<string>("chequing");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [includeConflicts, setIncludeConflicts] = useState(false);
  const [coverage, setCoverage] = useState<AccountCoverage[]>([]);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(() => {
    void api.importCoverage().then(setCoverage).catch(() => setCoverage([]));
    void api.importBatches().then(setBatches).catch(() => setBatches([]));
  }, []);

  useEffect(() => {
    void api.importPresets().then(setPresets).catch(() => setPresets([]));
    loadStatus();
  }, [loadStatus]);

  // Defaults to the first account once they load, without clobbering a real choice.
  const selected = accountChoice ?? (accounts.length ? String(accounts[0].id) : NEW_ACCOUNT);

  /** Resolve the target account, creating a manual one when that's the choice. */
  async function resolveAccountId(): Promise<number> {
    if (selected !== NEW_ACCOUNT) return Number(selected);
    const kind = ACCOUNT_KINDS.find((k) => k.key === newAccountKind) ?? ACCOUNT_KINDS[0];
    const created = await api.createManualAccount(
      newAccountName.trim() || "Manual account",
      kind.type,
      kind.subtype,
      null,
    );
    await refresh();
    setAccountChoice(String(created.id));
    return created.id;
  }

  async function onPreview(chosen: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const accountId = await resolveAccountId();
      setPreview(await api.previewImport(chosen, accountId, preset));
    } catch (e) {
      setPreview(null);
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onCommit() {
    if (!file || !preview) return;
    setBusy(true);
    setError(null);
    try {
      const committed = await api.commitImport(
        file,
        preview.account_id,
        preset,
        includeConflicts,
      );
      setResult(committed);
      setPreview(null);
      setFile(null);
      setIncludeConflicts(false);
      loadStatus();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setPreview(null);
    setResult(null);
    setFile(null);
    setError(null);
    setIncludeConflicts(false);
  }

  const importable = preview
    ? preview.new + (includeConflicts ? preview.conflict : 0)
    : 0;

  return (
    <>
      <Card
        title="Import a statement"
        sub="For accounts Plaid can't link — export a CSV or Excel file from your bank"
      >
        <div className="form-grid">
          <label>
            Account
            <select
              value={selected}
              onChange={(e) => {
                setAccountChoice(e.target.value);
                reset();
              }}
              disabled={busy || preview !== null}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name ?? `Account ${a.id}`}
                </option>
              ))}
              <option value={NEW_ACCOUNT}>+ New manual account…</option>
            </select>
          </label>

          {selected === NEW_ACCOUNT && (
            <>
              <label>
                New account name
                <input
                  value={newAccountName}
                  onChange={(e) => setNewAccountName(e.target.value)}
                  disabled={busy || preview !== null}
                />
              </label>
              <label>
                Kind
                <select
                  value={newAccountKind}
                  onChange={(e) => setNewAccountKind(e.target.value)}
                  disabled={busy || preview !== null}
                >
                  {ACCOUNT_KINDS.map((k) => (
                    <option key={k.key} value={k.key}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}

          <label>
            Format
            <select
              value={preset}
              onChange={(e) => {
                setPreset(e.target.value);
                reset();
              }}
              disabled={busy || preview !== null}
            >
              {presets.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            File
            <input
              type="file"
              accept=".csv,.xlsx,.xlsm,text/csv"
              disabled={busy}
              onChange={(e) => {
                const chosen = e.target.files?.[0] ?? null;
                setFile(chosen);
                setResult(null);
                if (chosen) void onPreview(chosen);
              }}
            />
          </label>
        </div>

        {busy && <p className="muted">Working…</p>}
        {error && <p className="error">{error}</p>}

        {result && (
          <div className="banner">
            Imported <strong>{result.imported}</strong> transactions covering{" "}
            {rangeLabel(result.period)}. Skipped {result.duplicate} already-stored{" "}
            {result.duplicate === 1 ? "row" : "rows"}.
          </div>
        )}
      </Card>

      {preview && (
        <Card
          title={`Preview — ${preview.filename}`}
          sub={`${preview.parsed} rows covering ${rangeLabel(preview.period)}`}
          action={
            <div className="topbar-actions">
              <button className="btn btn-ghost" onClick={reset} disabled={busy}>
                Cancel
              </button>
              <button className="btn" onClick={onCommit} disabled={busy || importable === 0}>
                Import {importable}
              </button>
            </div>
          }
        >
          <div className="grid grid-3">
            <div className="metric-tile">
              <div className="metric-label">New</div>
              <div className="metric-value sm">{preview.new}</div>
              <div className="metric-foot">will be added</div>
            </div>
            <div className="metric-tile">
              <div className="metric-label">Duplicate</div>
              <div className="metric-value sm">{preview.duplicate}</div>
              <div className="metric-foot">already stored — skipped</div>
            </div>
            <div className="metric-tile">
              <div className="metric-label">Conflicting</div>
              <div className="metric-value sm">{preview.conflict}</div>
              <div className="metric-foot">amount differs from stored</div>
            </div>
          </div>

          {preview.transfers > 0 && (
            <p className="muted">
              {preview.transfers} of these look like transfers between your own accounts
              (e.g. credit-card payments). They'll be categorized{" "}
              <strong>Transfers</strong> and left out of spending and income, so importing
              both sides of a payment doesn't double-count it. Recategorize any row to
              override.
            </p>
          )}

          <h3>Coverage after this import</h3>
          <GapList gaps={preview.gaps_after} />

          {preview.conflict > 0 && (
            <>
              <h3>Conflicts</h3>
              <p className="muted">
                A row matching the same date and description is already stored with a
                different amount. Skipped unless you include them.
              </p>
              <RowTable rows={preview.conflicts} />
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={includeConflicts}
                  onChange={(e) => setIncludeConflicts(e.target.checked)}
                />
                Import conflicting rows too
              </label>
            </>
          )}

          <h3>First rows</h3>
          <p className="muted">Check the dates and amounts parsed the way you expect.</p>
          <RowTable rows={preview.sample} />
        </Card>
      )}

      <Card title="Data coverage" sub="Which periods each account has data for">
        {coverage.length === 0 ? (
          <EmptyState>No accounts yet.</EmptyState>
        ) : (
          coverage.map((c) => (
            <div className="account-row" key={c.account_id}>
              <div>
                <div className="account-name">
                  {c.account_name ?? `Account ${c.account_id}`}{" "}
                  <span className="chip">{c.source}</span>
                </div>
                <div className="account-meta">
                  {c.covered.length === 0
                    ? "No data yet"
                    : c.covered.map(rangeLabel).join(", ")}
                </div>
                {c.source === "csv" ? (
                  <label className="inline-field">
                    Kind
                    <select
                      value={
                        ACCOUNT_KINDS.find((k) => k.type === c.account_type)?.key ??
                        "chequing"
                      }
                      onChange={async (e) => {
                        const kind = ACCOUNT_KINDS.find((k) => k.key === e.target.value);
                        if (!kind) return;
                        await api.updateManualAccount(c.account_id, {
                          type: kind.type,
                          subtype: kind.subtype,
                        });
                        loadStatus();
                        await refresh();
                      }}
                    >
                      {ACCOUNT_KINDS.map((k) => (
                        <option key={k.key} value={k.key}>
                          {k.label}
                        </option>
                      ))}
                    </select>
                    {c.account_type === "credit" || c.account_type === "loan" ? (
                      <span className="muted">counts as debt</span>
                    ) : (
                      <span className="muted">counts as an asset</span>
                    )}
                  </label>
                ) : null}
              </div>
              <GapList gaps={c.gaps} />
            </div>
          ))
        )}
      </Card>

      <Card title="Import history">
        {batches.length === 0 ? (
          <EmptyState>Nothing imported yet.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>File</th>
                <th>Period</th>
                <th className="num">Imported</th>
                <th className="num">Duplicate</th>
                <th className="num">Conflicting</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id}>
                  <td>{b.filename}</td>
                  <td>{rangeLabel({ start: b.period_start, end: b.period_end })}</td>
                  <td className="num">{b.rows_imported}</td>
                  <td className="num">{b.rows_duplicate}</td>
                  <td className="num">{b.rows_conflicting}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
