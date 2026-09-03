import TransactionsTable from "../components/TransactionsTable";
import { Card } from "../components/ui";
import { useFinance } from "../data/financeContext";

export default function Transactions() {
  const { transactions } = useFinance();
  return (
    <Card title="Transactions" sub={`${transactions.length} most recent`}>
      <TransactionsTable transactions={transactions} />
    </Card>
  );
}
