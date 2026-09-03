import type { Transaction } from "../api/client";
import { currency, shortDate } from "../lib/format";
import { EmptyState } from "./ui";

function CategoryCell({
  txn,
  categories,
  onRecategorize,
}: {
  txn: Transaction;
  categories?: string[];
  onRecategorize?: (id: number, category: string) => void;
}) {
  if (!categories || !onRecategorize) {
    return <span className="tag">{txn.category ?? "Uncategorized"}</span>;
  }
  const current = txn.category ?? "Uncategorized";
  const options = Array.from(new Set([current, ...categories]));
  return (
    <select
      className="cat-select"
      value={current}
      onChange={(e) => {
        if (e.target.value !== current) onRecategorize(txn.id, e.target.value);
      }}
    >
      {options.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
}

export default function TransactionsTable({
  transactions,
  categories,
  onRecategorize,
}: {
  transactions: Transaction[];
  categories?: string[];
  onRecategorize?: (id: number, category: string) => void;
}) {
  if (transactions.length === 0) {
    return <EmptyState>No transactions yet. Connect a bank and hit “Sync now”.</EmptyState>;
  }
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Description</th>
          <th>Category</th>
          <th className="num">Amount</th>
        </tr>
      </thead>
      <tbody>
        {transactions.map((t) => {
          const income = t.amount < 0; // Plaid: negative = money in
          return (
            <tr key={t.id}>
              <td className="muted">{shortDate(t.date)}</td>
              <td>
                {t.merchant_name ?? t.name ?? "—"}
                {t.pending && <span className="pending">pending</span>}
              </td>
              <td>
                <CategoryCell txn={t} categories={categories} onRecategorize={onRecategorize} />
              </td>
              <td className={`num ${income ? "amt-in" : "amt-out"}`}>
                {income ? "+" : ""}
                {currency(Math.abs(t.amount))}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
