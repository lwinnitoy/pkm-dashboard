import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type InvestmentDirection } from "../api/client";
import { CHART } from "../lib/charts";
import { currency, currencyCompact, currencyWhole, percent } from "../lib/format";
import { Card, EmptyState } from "./ui";

// A long-run nominal return for a low-cost all-equity ETF: FP Canada's 2026
// guidelines (~6.3% before fees for Canadian stocks, see the projection card on
// this page) rounded down a touch for fees.
const LONG_RUN_RETURN = 6;
const HORIZONS = [5, 10, 20, 30];
const STORAGE_KEY = "pkm.direction";

/** Future value of `start` plus `monthly` deposits, compounding monthly. */
function grow(start: number, monthly: number, annualPct: number, years: number): number {
  const r = Math.pow(1 + annualPct / 100, 1 / 12) - 1;
  const n = years * 12;
  const growth = Math.pow(1 + r, n);
  return start * growth + (Math.abs(r) < 1e-12 ? monthly * n : (monthly * (growth - 1)) / r);
}

// The monthly amount and horizon are the viewer's own what-ifs, so they're kept
// in this browser only; losing them just falls back to the detected defaults.
function loadSaved(): { monthly?: string; years?: string } {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

/**
 * "Where am I heading?" without having to set a goal first: today's investment
 * value, what's going in each month, and where that lands in N years — at a
 * long-run return and at the gain the holdings show so far.
 */
export default function DirectionCard() {
  const [data, setData] = useState<InvestmentDirection | null>(null);
  const [failed, setFailed] = useState(false);
  const saved = loadSaved();
  const [monthly, setMonthly] = useState<string | undefined>(saved.monthly);
  const [years, setYears] = useState(saved.years ?? "30");

  useEffect(() => {
    api.investmentDirection().then(setData).catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ monthly, years }));
    } catch {
      // Private mode / blocked storage: the inputs just won't be remembered.
    }
  }, [monthly, years]);

  if (failed) return null; // the goal card below still works without it
  if (data == null) {
    return (
      <Card title="Current direction">
        <EmptyState>Loading…</EmptyState>
      </Card>
    );
  }
  if (data.total_value == null) {
    return (
      <Card title="Current direction">
        <EmptyState>Link an investment account to see where your savings are heading.</EmptyState>
      </Card>
    );
  }

  const detected = data.monthly_contribution;
  const monthlyText = monthly ?? (detected != null ? String(Math.round(detected)) : "");
  const perMonth = Math.max(0, Number(monthlyText) || 0);
  const horizon = Math.min(60, Math.max(1, Math.round(Number(years) || 30)));
  const start = data.total_value;
  const gainPct = data.unrealized_gain_pct;
  const showGainLine = gainPct != null && gainPct > 0 && Math.abs(gainPct - LONG_RUN_RETURN) > 0.05;

  const thisYear = new Date().getFullYear();
  const series = Array.from({ length: horizon + 1 }, (_, y) => ({
    year: thisYear + y,
    longRun: Math.round(grow(start, perMonth, LONG_RUN_RETURN, y)),
    ...(showGainLine ? { atGain: Math.round(grow(start, perMonth, gainPct, y)) } : {}),
  }));
  const marks = [...new Set([...HORIZONS.filter((h) => h < horizon), horizon])];

  return (
    <Card
      title="Current direction"
      sub={`${data.account_names.join(", ")} — where it's heading at your current pace`}
    >
      <div className="form-grid direction-inputs">
        <label>
          Added per month $
          <input
            type="number"
            min={0}
            step={10}
            value={monthlyText}
            placeholder="0"
            onChange={(e) => setMonthly(e.target.value)}
          />
        </label>
        <label>
          Years
          <input
            type="number"
            min={1}
            max={60}
            value={years}
            onChange={(e) => setYears(e.target.value)}
          />
        </label>
        {monthly != null && detected != null && Number(monthly) !== Math.round(detected) && (
          <button className="link-plain" onClick={() => setMonthly(undefined)}>
            Use detected {currencyWhole(detected)}/mo
          </button>
        )}
      </div>
      <p className="direction-note">
        {detected != null
          ? `Detected about ${currencyWhole(detected)}/month going in: ${data.contribution_count} deposits and withdrawals over the last ${Math.round(data.history_days / 30.4)} months.`
          : `Not enough history to detect what you add each month yet (Plaid has ${data.history_days} day${data.history_days === 1 ? "" : "s"} of investment activity), so enter it above.`}
      </p>

      <div className="goal-stats">
        <div>
          <div className="metric-label">Today</div>
          <div className="metric-value sm">{currencyWhole(start)}</div>
        </div>
        {marks.map((h) => (
          <div key={h}>
            <div className="metric-label">In {h} years</div>
            <div className="metric-value sm">
              {currencyWhole(grow(start, perMonth, LONG_RUN_RETURN, h))}
            </div>
            {showGainLine && (
              <div className="cell-hint">{currencyWhole(grow(start, perMonth, gainPct, h))} at {percent(gainPct)}</div>
            )}
          </div>
        ))}
      </div>

      <div className="chart chart-200">
        <ResponsiveContainer>
          <LineChart data={series} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis
              tickFormatter={currencyCompact}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={54}
            />
            <Tooltip formatter={(v) => currency(Number(v))} />
            <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="longRun"
              name={`${LONG_RUN_RETURN}%/yr long-run`}
              stroke={CHART.brand}
              strokeWidth={2}
              dot={false}
            />
            {showGainLine && (
              <Line
                type="monotone"
                dataKey="atGain"
                name={`${percent(gainPct)}/yr (your gain so far)`}
                stroke={CHART.positive}
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={false}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="direction-note">
        In future dollars, before tax. The {LONG_RUN_RETURN}% line is a long-run assumption for a
        low-cost stock ETF.
        {showGainLine &&
          ` Your ${percent(gainPct)} is the total gain on what you've paid so far, not a yearly return, so treat that line as optimistic.`}
      </p>
    </Card>
  );
}
