import { useCallback, useEffect, useState } from "react";
import { api, type BudgetStatus, type BudgetStatusItem } from "../api/client";
import { Card, EmptyState, MetricTile } from "../components/ui";
import { CHART } from "../lib/charts";
import { currency } from "../lib/format";

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7);
}

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(month: string): string {
  const d = new Date(`${month}-01T00:00:00`);
  return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
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
  onSave: (category: string, limit: number) => void;
  onRemove: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(item.limit ?? ""));
  const pct = item.pct ?? 0;

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
              onChange={(e) => setValue(e.target.value)}
            />
            <button
              className="btn"
              onClick={() => {
                const n = Number(value);
                if (n > 0) onSave(item.category, n);
                setEditing(false);
              }}
            >
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
          <button className="link-plain" onClick={() => setEditing((s) => !s)}>
            {editing ? "Cancel" : "Edit"}
          </button>
          {item.budget_id != null && (
            <button className="link-danger" onClick={() => onRemove(item.budget_id!)}>
              Remove
            </button>
          )}
        </span>
      </div>
    </div>
  );
}

export default function Budgets() {
  const [month, setMonth] = useState(currentMonth());
  const [status, setStatus] = useState<BudgetStatus | null>(null);

  const load = useCallback(() => {
    api.budgetStatus(month).then(setStatus).catch(() => setStatus(null));
  }, [month]);
  useEffect(load, [load]);

  const save = async (category: string, limit: number) => {
    await api.upsertBudget(category, limit);
    load();
  };
  const remove = async (id: number) => {
    await api.deleteBudget(id);
    load();
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
            <button className="btn-ghost btn" onClick={() => setMonth((m) => shiftMonth(m, -1))}>
              ‹
            </button>
            <span className="month-label">{monthLabel(month)}</span>
            <button
              className="btn-ghost btn"
              onClick={() => setMonth((m) => shiftMonth(m, 1))}
              disabled={month >= currentMonth()}
            >
              ›
            </button>
          </div>
          <div className="month-totals">
            <MetricTile label="Spent" value={currency(totalSpent)} small />
            <MetricTile label="Budgeted" value={currency(totalLimit)} small />
            <MetricTile
              label="Remaining"
              value={currency(totalLimit - totalSpent)}
              small
            />
          </div>
        </div>
      </Card>

      <Card title="Budgets" sub="Monthly limits per category">
        {budgeted.length === 0 ? (
          <EmptyState>No budgets yet. Set one on a category below.</EmptyState>
        ) : (
          budgeted.map((i) => (
            <BudgetRow key={i.category} item={i} onSave={save} onRemove={remove} />
          ))
        )}
      </Card>

      <Card title="Not budgeted" sub="Categories with spending this month">
        {unbudgeted.length === 0 ? (
          <EmptyState>Every category with spending has a budget. 🎯</EmptyState>
        ) : (
          unbudgeted.map((i) => (
            <BudgetRow key={i.category} item={i} onSave={save} onRemove={remove} />
          ))
        )}
      </Card>
    </>
  );
}
