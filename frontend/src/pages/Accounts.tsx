import PlaidLinkButton from "../components/PlaidLinkButton";
import { Card, EmptyState } from "../components/ui";
import { useFinance } from "../data/financeContext";
import { currency } from "../lib/format";

export default function Accounts() {
  const { accounts, refresh } = useFinance();

  return (
    <Card
      title="Linked accounts"
      sub={accounts.length ? `${accounts.length} accounts` : undefined}
      action={<PlaidLinkButton onLinked={refresh} />}
    >
      {accounts.length === 0 ? (
        <EmptyState>
          No accounts linked yet. Use “Connect a bank” to link one via Plaid.
        </EmptyState>
      ) : (
        <div>
          {accounts.map((a) => (
            <div className="account-row" key={a.id}>
              <div>
                <div className="account-name">{a.name ?? "Account"}</div>
                <div className="account-meta">
                  {[a.official_name, a.subtype ?? a.type].filter(Boolean).join(" · ")}
                </div>
              </div>
              <div>{currency(a.current_balance)}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
