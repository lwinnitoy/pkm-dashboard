// Thin typed wrapper around fetch to the FastAPI backend.
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// --- Auth token storage (single-user bearer token from /api/auth/login) ---
const TOKEN_KEY = "pkm_token";
export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string): void => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = (): void => localStorage.removeItem(TOKEN_KEY);

export interface Transaction {
  id: number;
  date: string;
  name: string | null;
  merchant_name: string | null;
  amount: number;
  currency: string | null;
  category: string | null;
  pending: boolean;
}

export interface CategorySpend {
  category: string;
  total: number;
  count: number;
}

export interface Summary {
  period_days: number;
  total_spent: number;
  transaction_count: number;
  by_category: CategorySpend[];
}

export interface Account {
  id: number;
  name: string | null;
  official_name: string | null;
  type: string | null;
  subtype: string | null;
  current_balance: number | null;
  currency: string | null;
}

export interface TrendPoint {
  period_start: string;
  spent: number;
  income: number;
}

export interface MerchantSpend {
  merchant: string;
  total: number;
  count: number;
}

export interface CategoryComparison {
  category: string;
  current: number;
  previous: number;
  pct_change: number | null;
}

export interface NetWorthPoint {
  date: string;
  assets: number;
  liabilities: number;
  net_worth: number;
}

export interface AccountValue {
  account_id: number;
  account_name: string | null;
  value: number;
}

export interface PortfolioHolding {
  ticker: string | null;
  security_name: string | null;
  value: number;
}

export interface PortfolioSummary {
  // total_value can be null per the app contract ("no investments linked").
  total_value: number | null;
  holdings_count: number;
  by_account: AccountValue[];
  top_holdings: PortfolioHolding[];
}

export interface Holding {
  account_id: number;
  account_name: string | null;
  ticker: string | null;
  security_name: string | null;
  quantity: number | null;
  price: number | null;
  value: number | null;
  cost_basis: number | null;
  currency: string | null;
}

export interface InvestmentTransaction {
  id: number;
  date: string;
  name: string | null;
  ticker: string | null;
  type: string | null;
  subtype: string | null;
  quantity: number | null;
  price: number | null;
  amount: number | null;
  fees: number | null;
  currency: string | null;
}

export interface Budget {
  id: number;
  category: string;
  monthly_limit: number;
}

export interface BudgetStatusItem {
  budget_id: number | null;
  category: string;
  limit: number | null;
  spent: number;
  remaining: number | null;
  pct: number | null;
}

export interface BudgetStatus {
  month: string;
  total_limit: number;
  total_spent: number;
  items: BudgetStatusItem[];
}

export interface Goal {
  id: number;
  name: string;
  target_amount: number;
  target_date: string;
  expected_annual_return: number;
  monthly_contribution: number;
  current_value: number | null;
  projected_value: number | null;
  gap: number | null;
  on_track: boolean | null;
  required_monthly_contribution: number | null;
}

export interface GoalInput {
  name: string;
  target_amount: number;
  target_date: string;
  expected_annual_return: number;
  monthly_contribution: number;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (res.status === 401) {
    // Token missing/expired — drop it and bounce back to the login screen.
    clearToken();
    window.location.reload();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  authStatus: () => req<{ auth_required: boolean }>("/api/auth/status"),

  // Login handles its own response (a 401 here means "wrong password", not an
  // expired session), so it bypasses the global 401 → reload behavior above.
  login: async (password: string): Promise<void> => {
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      throw new Error(res.status === 401 ? "Incorrect password" : `Login failed (${res.status})`);
    }
    const { token } = (await res.json()) as { token: string };
    setToken(token);
  },

  createLinkToken: () =>
    req<{ link_token: string }>("/api/plaid/create-link-token", { method: "POST" }),

  exchangeToken: (public_token: string, institution_name?: string) =>
    req<{ item_id: string; accounts_linked: number }>("/api/plaid/exchange-token", {
      method: "POST",
      body: JSON.stringify({ public_token, institution_name }),
    }),

  sync: () =>
    req<{ added: number; modified: number; removed: number }>("/api/plaid/sync", {
      method: "POST",
    }),

  investmentsSync: () =>
    req<{ items_synced: number; items_skipped: number }>("/api/investments/sync", {
      method: "POST",
    }),

  transactions: (limit = 50) =>
    req<Transaction[]>(`/api/finance/transactions?limit=${limit}`),

  recategorize: (id: number, category: string) =>
    req<Transaction>(`/api/finance/transactions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ category }),
    }),

  categories: () => req<string[]>("/api/finance/categories"),

  budgetStatus: (month?: string) =>
    req<BudgetStatus>(`/api/finance/budgets/status${month ? `?month=${month}` : ""}`),

  upsertBudget: (category: string, monthly_limit: number) =>
    req<Budget>("/api/finance/budgets", {
      method: "POST",
      body: JSON.stringify({ category, monthly_limit }),
    }),

  deleteBudget: (id: number) =>
    req<void>(`/api/finance/budgets/${id}`, { method: "DELETE" }),

  summary: (period = 30) => req<Summary>(`/api/finance/summary?period=${period}`),

  accounts: () => req<Account[]>("/api/finance/accounts"),

  spendingTrend: (period = 180, granularity: "day" | "week" | "month" = "month") =>
    req<TrendPoint[]>(
      `/api/finance/spending-trend?period=${period}&granularity=${granularity}`,
    ),

  topMerchants: (period = 30, limit = 10) =>
    req<MerchantSpend[]>(`/api/finance/top-merchants?period=${period}&limit=${limit}`),

  categoryComparison: (days = 30) =>
    req<CategoryComparison[]>(`/api/finance/category-comparison?days=${days}`),

  netWorth: (period = 180) =>
    req<NetWorthPoint[]>(`/api/finance/net-worth?period=${period}`),

  investmentsPortfolio: () =>
    req<PortfolioSummary>("/api/investments/portfolio"),

  holdings: () => req<Holding[]>("/api/investments/holdings"),

  investmentTransactions: (limit = 50) =>
    req<InvestmentTransaction[]>(`/api/investments/transactions?limit=${limit}`),

  goals: () => req<Goal[]>("/api/finance/goals"),

  createGoal: (goal: GoalInput) =>
    req<Goal>("/api/finance/goals", {
      method: "POST",
      body: JSON.stringify(goal),
    }),

  updateGoal: (id: number, patch: Partial<GoalInput>) =>
    req<Goal>(`/api/finance/goals/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteGoal: (id: number) =>
    req<void>(`/api/finance/goals/${id}`, { method: "DELETE" }),
};
