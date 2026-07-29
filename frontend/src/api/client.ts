// Thin typed wrapper around fetch to the FastAPI backend.
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
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

  transactions: (limit = 50) =>
    req<Transaction[]>(`/api/finance/transactions?limit=${limit}`),

  summary: (period = 30) => req<Summary>(`/api/finance/summary?period=${period}`),

  accounts: () => req<Account[]>("/api/finance/accounts"),
};
