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

export interface ImportPreset {
  key: string;
  label: string;
}

export interface DateRange {
  start: string;
  end: string;
}

export interface ImportRow {
  date: string;
  description: string;
  amount: number;
  currency: string | null;
  status: "new" | "duplicate" | "conflict";
  existing_amount: number | null;
  category: string;
}

export interface ImportPreview {
  account_id: number;
  filename: string;
  preset: string;
  period: DateRange;
  parsed: number;
  new: number;
  duplicate: number;
  conflict: number;
  transfers: number;
  gaps_before: DateRange[];
  gaps_after: DateRange[];
  conflicts: ImportRow[];
  sample: ImportRow[];
}

export interface ImportResult {
  batch_id: number;
  imported: number;
  duplicate: number;
  conflict: number;
  period: DateRange;
  gaps: DateRange[];
}

export interface ImportBatch {
  id: number;
  account_id: number;
  filename: string;
  preset: string;
  period_start: string;
  period_end: string;
  rows_parsed: number;
  rows_imported: number;
  rows_duplicate: number;
  rows_conflicting: number;
}

export interface AccountCoverage {
  account_id: number;
  account_name: string | null;
  account_type: string | null;
  source: string;
  covered: DateRange[];
  gaps: DateRange[];
  last_imported_period_end: string | null;
}

export interface GoalInput {
  name: string;
  target_amount: number;
  target_date: string;
  expected_annual_return: number;
  monthly_contribution: number;
}

async function handle<T>(res: Response): Promise<T> {
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

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  return handle<T>(
    await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    }),
  );
}

/** Multipart POST. Content-Type is left unset so the browser adds the boundary. */
async function upload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  return handle<T>(
    await fetch(`${BASE}${path}`, {
      method: "POST",
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }),
  );
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
    req<{
      items_synced: number;
      items_skipped: number;
      holdings: number;
      skipped_details: { institution: string; error_code: string; message: string }[];
    }>("/api/investments/sync", { method: "POST" }),

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

  // --- Manual statement import (for banks Plaid can't link, e.g. RBC) ---

  importPresets: () => req<ImportPreset[]>("/api/imports/presets"),

  createManualAccount: (
    name: string,
    type: string,
    subtype: string | null,
    current_balance: number | null,
  ) =>
    req<Account>("/api/imports/accounts", {
      method: "POST",
      body: JSON.stringify({ name, type, subtype, current_balance }),
    }),

  updateManualAccount: (id: number, patch: { type?: string; subtype?: string | null }) =>
    req<Account>(`/api/imports/accounts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  previewImport: (file: File, accountId: number, preset: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("account_id", String(accountId));
    form.append("preset", preset);
    return upload<ImportPreview>("/api/imports/preview", form);
  },

  commitImport: (file: File, accountId: number, preset: string, includeConflicts: boolean) => {
    const form = new FormData();
    form.append("file", file);
    form.append("account_id", String(accountId));
    form.append("preset", preset);
    form.append("include_conflicts", String(includeConflicts));
    return upload<ImportResult>("/api/imports/commit", form);
  },

  importCoverage: () => req<AccountCoverage[]>("/api/imports/coverage"),

  importBatches: () => req<ImportBatch[]>("/api/imports/batches"),
};
