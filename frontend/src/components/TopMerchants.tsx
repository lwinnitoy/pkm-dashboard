import type { MerchantSpend } from "../api/client";
import { currency } from "../lib/format";
import { EmptyState } from "./ui";

export default function TopMerchants({ data }: { data: MerchantSpend[] }) {
  const max = data.reduce((m, d) => Math.max(m, d.total), 0);
  if (data.length === 0) return <EmptyState>No spending in this window.</EmptyState>;
  return (
    <ul className="merchant-list">
      {data.map((m) => (
        <li key={m.merchant}>
          <div className="merchant-row">
            <span className="merchant-name">{m.merchant}</span>
            <span>{currency(m.total)}</span>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${max ? (m.total / max) * 100 : 0}%` }} />
          </div>
          <span className="merchant-count">{m.count} txns</span>
        </li>
      ))}
    </ul>
  );
}
