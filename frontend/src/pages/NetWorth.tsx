import type { Account } from "../api/client";
import NetWorthChart from "../components/NetWorthChart";
import { Card, EmptyState, MetricTile } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { currency, currencyWhole } from "../lib/format";

function isLiability(a: Account): boolean {
  return /credit|loan/i.test(a.type ?? "");
}

function AccountList({ accounts }: { accounts: Account[] }) {
  if (accounts.length === 0) return <EmptyState>None linked.</EmptyState>;
  return (
    <div>
      {accounts.map((a) => (
        <div className="account-row" key={a.id}>
          <div>
            <div className="account-name">{a.name ?? "Account"}</div>
            <div className="account-meta">{a.subtype ?? a.type ?? ""}</div>
          </div>
          <div>{currency(a.current_balance)}</div>
        </div>
      ))}
    </div>
  );
}

export default function NetWorth() {
  const { netWorth, accounts } = useFinance();
  const latest = netWorth.length > 0 ? netWorth[netWorth.length - 1] : null;
  const assets = accounts.filter((a) => !isLiability(a));
  const liabilities = accounts.filter(isLiability);

  return (
    <>
      <div className="grid grid-3">
        <Card>
          <MetricTile label="Net worth" value={latest ? currencyWhole(latest.net_worth) : "—"} />
        </Card>
        <Card>
          <MetricTile label="Assets" value={latest ? currencyWhole(latest.assets) : "—"} />
        </Card>
        <Card>
          <MetricTile
            label="Liabilities"
            value={latest ? currencyWhole(latest.liabilities) : "—"}
          />
        </Card>
      </div>

      <Card title="Net worth over time">
        <NetWorthChart data={netWorth} />
      </Card>

      <div className="grid grid-2">
        <Card title="Assets">
          <AccountList accounts={assets} />
        </Card>
        <Card title="Liabilities">
          <AccountList accounts={liabilities} />
        </Card>
      </div>
    </>
  );
}
