import GoalsCard from "../components/GoalsCard";
import InsightsPanel from "../components/InsightsPanel";
import { useFinance } from "../data/financeContext";

export default function Goals() {
  const { goals, createGoal, deleteGoal } = useFinance();
  return (
    <>
      <GoalsCard goals={goals} onCreate={createGoal} onDelete={deleteGoal} />
      <InsightsPanel
        page="goals"
        title="Learn: retirement goals"
        sub="How much is enough, what CPP and OAS cover, and which accounts to use first"
      />
    </>
  );
}
