// Small derivations shared across pages (savings rate, cash-flow totals,
// net-worth change) so the same numbers appear everywhere.
import type { NetWorthPoint, TrendPoint } from "../api/client";

export function cashFlowTotals(trend: TrendPoint[]): { income: number; spending: number } {
  return trend.reduce(
    (acc, p) => ({ income: acc.income + p.income, spending: acc.spending + p.spent }),
    { income: 0, spending: 0 },
  );
}

/** Percentage of income kept. Null when there's no income to divide by. */
export function savingsRate(income: number, spending: number): number | null {
  if (income <= 0) return null;
  return ((income - spending) / income) * 100;
}

export interface NetWorthChange {
  latest: number;
  changeAbs: number;
  changePct: number | null;
}

/** Change across the currently-loaded net-worth series (first → last point). */
export function netWorthChange(series: NetWorthPoint[]): NetWorthChange | null {
  if (series.length === 0) return null;
  const latest = series[series.length - 1].net_worth;
  const first = series[0].net_worth;
  const changeAbs = latest - first;
  const changePct = first !== 0 ? (changeAbs / Math.abs(first)) * 100 : null;
  return { latest, changeAbs, changePct };
}
