import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText, type BudgetStatus, type BudgetStatusItem } from "../api/client";
import InsightsPanel from "../components/InsightsPanel";
import { Card, EmptyState, MetricTile } from "../components/ui";
import { CHART } from "../lib/charts";
import { monthKey, parseDate } from "../lib/dates";
import { currency } from "../lib/format";

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  return monthKey(new Date(y, m - 1 + delta, 1));
}

function monthLabel(month: string): string {
  return parseDate(`${month}-01`).toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

function barColor(pct: number | null): string {
  if (pct == null) return CHART.neutral;
  if (pct >= 100) return CHART.negative;
  if (pct >= 80) return "#f59e0b";
  return CHART.positive;
}

function BudgetRow({
  item,
  onSave,
  onRemove,
}: {
  item: BudgetStatusItem;
  onSave: (category: string, limit: number) => Promise<void>;
  onRemove: (id: number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(item.limit ?? ""));
  const [error, setError] = useState<string | null>(null);
  const pct = item.pct ?? 0;
  const budgetId = item.budget_id;

  const save = async () => {
    const n = Number(value);
    if (!(n > 0)) {
      setError("Enter a monthly limit above zero.");
      return;
    }
    try {
      await onSave(item.category, n);
      setError(null);
      setEditing(false);
    } catch (e) {
      setError(`Couldn't save: ${errorText(e)}`);
    }
  };
  const remove = async (id: number) => {
    try {
      await onRemove(id);
    } catch (e) {
      setError(`Couldn't remove: ${errorText(e)}`);
    }
  };

  return (
    <div className="budget-row">
      <div className="budget-row-head">
        <span className="account-name">{item.category}</span>
        {editing ? (
          <span className="budget-edit">
            <input
              type="number"
              value={value}
              autoFocus
              aria-label={`Monthly limit for ${item.category}`}
              onChange={(e) => setValue(e.target.value)}
            />
            <button className="btn" onClick={save}>
              Save
            </button>
          </span>
        ) : (
          <span className="muted">
            {currency(item.spent)} of {currency(item.limit)}
          </span>
        )}
      </div>
      <div className="bar-track">
        <div
          className="bar-fill"
          style={{ width: `${Math.min(100, pct)}%`, background: barColor(item.pct) }}
        />
      </div>
      <div className="budget-row-foot">
        <span className={(item.remaining ?? 0) < 0 ? "amt-out" : "amt-in"}>
          {(item.remaining ?? 0) < 0
            ? `${currency(Math.abs(item.remaining ?? 0))} over`
            : `${currency(item.remaining)} left`}
        </span>
        <span className="budget-actions">
          <button
            className="link-plain"
            onClick={() => {
              setEditing((s) => !s);
              setError(null);
            }}
          >
            {editing ? "Cancel" : "Edit"}
          </button>
          {budgetId != null && (
            <button className="link-danger" onClick={() => remove(budgetId)}>
              Remove
            </button>
          )}
        </span>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

export default function Budgets() {
  const [month, setMonth] = useState(() => monthKey());
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Clicking ‹ quickly starts several fetches; only the newest may land, or the
  // label and the numbers can disagree about the month.
  const latest = useRef(0);
  const load = useCallback(async () => {
    const id = ++latest.current;
    try {
      const next = await api.budgetStatus(month);
      if (id !== latest.current) return;
      setStatus(next);
      setError(null);
    } catch (e) {
      if (id === latest.current) setError(errorText(e));
    }
  }, [month]);
  useEffect(() => {
    setStatus(null);
    load();
  }, [load]);

  const save = async (category: string, limit: number) => {
    await api.upsertBudget(category, limit);
    await load();
  };
  const remove = async (id: number) => {
    await api.deleteBudget(id);
    await load();
  };

  const items = status?.items ?? [];
  const budgeted = items.filter((i) => i.limit != null);
  const unbudgeted = items.filter((i) => i.limit == null);
  const totalSpent = status?.total_spent ?? 0;
  const totalLimit = status?.total_limit ?? 0;

  return (
    <>
      <Card>
        <div className="month-bar">
          <div className="month-nav">
            <button
              className="btn-ghost btn"
              aria-label="Previous month"
              onClick={() => setMonth((m) => shiftMonth(m, -1))}
            >
              ‹
            </button>
            <span className="month-label">{monthLabel(month)}</span>
            <button
              className="btn-ghost btn"
              aria-label="Next month"
              onClick={() => setMonth((m) => shiftMonth(m, 1))}
              disabled={month >= monthKey()}
            >
              ›
            </button>
          </div>
          <div className="month-totals">
            {/* "—" until this month's numbers arrive, rather than a believable $0.00. */}
            <MetricTile label="Spent" value={currency(status && totalSpent)} small />
            <MetricTile label="Budgeted" value={currency(status && totalLimit)} small />
            <MetricTile
              label="Remaining"
              value={currency(status && totalLimit - totalSpent)}
              small
            />
          </div>
        </div>
      </Card>

      {error && (
        <div className="banner error" role="alert">
          Couldn't load budgets: {error}
        </div>
      )}

      <Card title="Budgets" sub="Monthly limits per category">
        {status == null ? (
          <EmptyState>{error ? "—" : "Loading…"}</EmptyState>
        ) : budgeted.length === 0 ? (
          <EmptyState>
            {unbudgeted.length > 0
              ? "No budgets yet. Set one on a category below."
              : "No budgets yet. Categories you spend in will appear below, ready for a limit."}
          </EmptyState>
        ) : (
          budgeted.map((i) => (
            <BudgetRow key={i.category} item={i} onSave={save} onRemove={remove} />
          ))
        )}
      </Card>

      <Card title="Not budgeted" sub="Categories with spending this month">
        {status == null ? (
          <EmptyState>{error ? "—" : "Loading…"}</EmptyState>
        ) : unbudgeted.length === 0 ? (
          <EmptyState>
            {totalSpent > 0
              ? "Every category with spending has a budget. 🎯"
              : "No spending recorded for this month yet."}
          </EmptyState>
        ) : (
          unbudgeted.map((i) => (
            <BudgetRow key={i.category} item={i} onSave={save} onRemove={remove} />
          ))
        )}
      </Card>

      <InsightsPanel
        page="budgets"
        title="Learn: budgeting"
        sub="Common ways to split your income, and a plan for co-op work and study terms"
      />
    </>
  );
}
