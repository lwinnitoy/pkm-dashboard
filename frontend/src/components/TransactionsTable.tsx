import type { Transaction } from "../api/client";

export default function TransactionsTable({ transactions }: { transactions: Transaction[] }) {
  if (transactions.length === 0) {
    return <p className="muted">No transactions yet. Connect a bank and hit “Sync now”.</p>;
  }

  return (
    <table className="txn-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Description</th>
          <th>Category</th>
          <th style={{ textAlign: "right" }}>Amount</th>
        </tr>
      </thead>
      <tbody>
        {transactions.map((t) => (
          <tr key={t.id}>
            <td>{t.date}</td>
            <td>
              {t.merchant_name ?? t.name ?? "—"}
              {t.pending && <span className="pending"> pending</span>}
            </td>
            <td>{t.category ?? "Uncategorized"}</td>
            <td style={{ textAlign: "right" }} className={t.amount < 0 ? "credit" : ""}>
              {t.amount < 0 ? "+" : ""}${Math.abs(t.amount).toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
