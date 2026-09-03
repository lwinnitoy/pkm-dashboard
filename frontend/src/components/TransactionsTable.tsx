import type { Transaction } from "../api/client";
import { currency, shortDate } from "../lib/format";
import { EmptyState } from "./ui";

export default function TransactionsTable({
  transactions,
}: {
  transactions: Transaction[];
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
                <span className="tag">{t.category ?? "Uncategorized"}</span>
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
