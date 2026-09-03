import TransactionsTable from "../components/TransactionsTable";
import { Card } from "../components/ui";
import { useFinance } from "../data/financeContext";

export default function Transactions() {
  const { transactions, categories, recategorize } = useFinance();
  return (
    <Card
      title="Transactions"
      sub="Click a category to recategorize — it becomes a merchant rule for past and future"
    >
      <TransactionsTable
        transactions={transactions}
        categories={categories}
        onRecategorize={recategorize}
      />
    </Card>
  );
}
