import type { MerchantSpend } from "../api/client";

export default function TopMerchants({ data }: { data: MerchantSpend[] }) {
  const max = data.reduce((m, d) => Math.max(m, d.total), 0);
  return (
    <section className="card">
      <h2>Top merchants (30d)</h2>
      {data.length === 0 ? (
        <p className="muted">No spending in this window.</p>
      ) : (
        <ul className="merchant-list">
          {data.map((m) => (
            <li key={m.merchant}>
              <div className="merchant-row">
                <span className="merchant-name">{m.merchant}</span>
                <span className="merchant-total">${m.total.toFixed(2)}</span>
              </div>
              <div className="merchant-bar-track">
                <div
                  className="merchant-bar-fill"
                  style={{ width: `${max ? (m.total / max) * 100 : 0}%` }}
                />
              </div>
              <span className="muted merchant-count">{m.count} txns</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
