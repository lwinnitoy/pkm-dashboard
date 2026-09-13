import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Goal, GoalInput } from "../api/client";
import { CHART } from "../lib/charts";
import { currency, currencyCompact, currencyWhole } from "../lib/format";
import { EmptyState } from "./ui";

/** Compound-growth curve mirroring the backend projection, for display only. */
function projectionSeries(goal: Goal): { year: number; value: number }[] {
  if (goal.current_value == null) return [];
  const now = new Date();
  const target = new Date(goal.target_date);
  const totalMonths = Math.max(
    0,
    (target.getFullYear() - now.getFullYear()) * 12 + (target.getMonth() - now.getMonth()),
  );
  const r = Math.pow(1 + goal.expected_annual_return, 1 / 12) - 1;
  const pts: { year: number; value: number }[] = [];
  for (let m = 0; m <= totalMonths; m += 12) {
    const growth = Math.pow(1 + r, m);
    const annuity = Math.abs(r) < 1e-9 ? m : (growth - 1) / r;
    const value = goal.current_value * growth + goal.monthly_contribution * annuity;
    pts.push({ year: now.getFullYear() + Math.round(m / 12), value: Math.round(value) });
  }
  return pts;
}

const EMPTY: GoalInput = {
  name: "",
  target_amount: 1000000,
  target_date: "2050-01-01",
  expected_annual_return: 0.06,
  monthly_contribution: 1000,
};

export default function GoalsCard({
  goals,
  onCreate,
  onDelete,
}: {
  goals: Goal[];
  onCreate: (g: GoalInput) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [form, setForm] = useState<GoalInput>(EMPTY);
  const [showForm, setShowForm] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onCreate(form);
    setForm(EMPTY);
    setShowForm(false);
  };

  return (
    <section className="card">
      <div className="card-head">
        <h2>Retirement goals</h2>
        <button className="btn-ghost btn" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "Add goal"}
        </button>
      </div>

      {showForm && (
        <form className="form-grid" onSubmit={submit}>
          <label>
            Name
            <input
              value={form.name}
              required
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label>
            Target $
            <input
              type="number"
              value={form.target_amount}
              onChange={(e) => setForm({ ...form, target_amount: Number(e.target.value) })}
            />
          </label>
          <label>
            Target date
            <input
              type="date"
              value={form.target_date}
              onChange={(e) => setForm({ ...form, target_date: e.target.value })}
            />
          </label>
          <label>
            Return %/yr
            <input
              type="number"
              step="0.01"
              value={form.expected_annual_return}
              onChange={(e) =>
                setForm({ ...form, expected_annual_return: Number(e.target.value) })
              }
            />
          </label>
          <label>
            Contribution $/mo
            <input
              type="number"
              value={form.monthly_contribution}
              onChange={(e) =>
                setForm({ ...form, monthly_contribution: Number(e.target.value) })
              }
            />
          </label>
          <button type="submit" className="btn">
            Save goal
          </button>
        </form>
      )}

      {goals.length === 0 && !showForm && (
        <EmptyState>No goals yet. Add a retirement target to see your projection.</EmptyState>
      )}

      {goals.map((g) => {
        const series = projectionSeries(g);
        return (
          <div key={g.id} className="goal">
            <div className="goal-head">
              <div>
                <strong>{g.name}</strong>{" "}
                <span className="muted">
                  {currencyWhole(g.target_amount)} by {g.target_date}
                </span>
              </div>
              <button className="link-danger" onClick={() => onDelete(g.id)}>
                Delete
              </button>
            </div>

            {g.current_value == null ? (
              <EmptyState>Connect an investment account to project this goal.</EmptyState>
            ) : (
              <>
                <div className="goal-stats">
                  <div>
                    <div className="metric-label">Current</div>
                    <div className="metric-value sm">{currencyWhole(g.current_value)}</div>
                  </div>
                  <div>
                    <div className="metric-label">Projected at target</div>
                    <div className="metric-value sm">{currencyWhole(g.projected_value)}</div>
                  </div>
                  <div>
                    <div className="metric-label">Status</div>
                    <div className={g.on_track ? "badge-ok" : "badge-warn"}>
                      {g.on_track ? "On track" : "Shortfall"}
                    </div>
                  </div>
                  <div>
                    <div className="metric-label">Need / mo</div>
                    <div className="metric-value sm">
                      {currencyWhole(g.required_monthly_contribution)}
                    </div>
                  </div>
                </div>

                {series.length > 0 && (
                  <div className="chart chart-200">
                    <ResponsiveContainer>
                      <LineChart data={series} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
                        <CartesianGrid stroke={CHART.grid} vertical={false} />
                        <XAxis
                          dataKey="year"
                          tick={{ fontSize: 11 }}
                          tickLine={false}
                          axisLine={false}
                        />
                        <YAxis
                          tickFormatter={currencyCompact}
                          tick={{ fontSize: 11 }}
                          tickLine={false}
                          axisLine={false}
                          width={54}
                        />
                        <Tooltip formatter={(v) => currency(Number(v))} />
                        <ReferenceLine
                          y={g.target_amount}
                          stroke={CHART.negative}
                          strokeDasharray="4 4"
                          label={{ value: "Target", fontSize: 11, position: "insideTopRight" }}
                        />
                        <Line
                          type="monotone"
                          dataKey="value"
                          stroke={CHART.brand}
                          strokeWidth={2}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}
    </section>
  );
}
