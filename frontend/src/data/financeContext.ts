import { createContext, useContext } from "react";
import type {
  Account,
  CategoryComparison,
  Goal,
  GoalInput,
  MerchantSpend,
  NetWorthPoint,
  PortfolioSummary,
  Summary,
  Transaction,
  TrendPoint,
} from "../api/client";

/** Global date-range options (in days) shown in the topbar segmented control. */
export const RANGE_OPTIONS = [
  { days: 30, label: "30D" },
  { days: 90, label: "90D" },
  { days: 180, label: "6M" },
  { days: 365, label: "1Y" },
] as const;

/** Trend granularity scales with the selected range so charts stay legible. */
export function granularityFor(days: number): "day" | "week" | "month" {
  if (days <= 31) return "day";
  if (days <= 120) return "week";
  return "month";
}

export interface FinanceContextValue {
  loading: boolean;
  error: string | null;
  message: string | null;
  syncing: boolean;
  range: number;
  setRange: (days: number) => void;

  summary: Summary | null;
  transactions: Transaction[];
  accounts: Account[];
  trend: TrendPoint[];
  merchants: MerchantSpend[];
  comparison: CategoryComparison[];
  netWorth: NetWorthPoint[];
  goals: Goal[];
  portfolio: PortfolioSummary | null;
  categories: string[];

  refresh: () => Promise<void>;
  sync: () => Promise<void>;
  recategorize: (id: number, category: string) => Promise<void>;
  createGoal: (g: GoalInput) => Promise<void>;
  deleteGoal: (id: number) => Promise<void>;
}

export const FinanceContext = createContext<FinanceContextValue | null>(null);

export function useFinance(): FinanceContextValue {
  const ctx = useContext(FinanceContext);
  if (!ctx) throw new Error("useFinance must be used within <FinanceProvider>");
  return ctx;
}
