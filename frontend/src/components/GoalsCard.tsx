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
      <div className="summary-head">
        <h2>Retirement goals</h2>
        <button onClick={() => setShowForm((s) => !s)}>{showForm ? "Cancel" : "Add goal"}</button>
      </div>

      {showForm && (
        <form className="goal-form" onSubmit={submit}>
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
          <button type="submit">Save goal</button>
        </form>
      )}

      {goals.length === 0 && !showForm && (
        <p className="muted">No goals yet. Add a retirement target to see your projection.</p>
      )}

      {goals.map((g) => {
        const series = projectionSeries(g);
        return (
          <div key={g.id} className="goal">
            <div className="goal-head">
              <div>
                <strong>{g.name}</strong>{" "}
                <span className="muted">
                  ${g.target_amount.toLocaleString()} by {g.target_date}
                </span>
              </div>
              <button className="link-danger" onClick={() => onDelete(g.id)}>
                Delete
              </button>
            </div>

            {g.current_value == null ? (
              <p className="muted">
                Connect an investment account to project this goal.
              </p>
            ) : (
              <>
                <div className="goal-stats">
                  <div>
                    <div className="metric-label">Current</div>
                    <div className="metric-value">${g.current_value.toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="metric-label">Projected at target</div>
                    <div className="metric-value">
                      ${g.projected_value?.toLocaleString() ?? "—"}
                    </div>
                  </div>
                  <div>
                    <div className="metric-label">Status</div>
                    <div className={g.on_track ? "badge-ok" : "badge-warn"}>
                      {g.on_track ? "On track" : "Shortfall"}
                    </div>
                  </div>
                  <div>
                    <div className="metric-label">Need / mo</div>
                    <div className="metric-value">
                      ${g.required_monthly_contribution?.toLocaleString() ?? "—"}
                    </div>
                  </div>
                </div>

                {series.length > 0 && (
                  <div style={{ width: "100%", height: 200 }}>
                    <ResponsiveContainer>
                      <LineChart data={series} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} width={70} />
                        <Tooltip formatter={(v) => `$${Number(v).toLocaleString()}`} />
                        <ReferenceLine
                          y={g.target_amount}
                          stroke="#dc2626"
                          strokeDasharray="4 4"
                          label={{ value: "Target", fontSize: 11, position: "insideTopRight" }}
                        />
                        <Line
                          type="monotone"
                          dataKey="value"
                          name="Projected"
                          stroke="#4f46e5"
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
