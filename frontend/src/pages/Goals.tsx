import GoalsCard from "../components/GoalsCard";
import { useFinance } from "../data/financeContext";

export default function Goals() {
  const { goals, createGoal, deleteGoal } = useFinance();
  return <GoalsCard goals={goals} onCreate={createGoal} onDelete={deleteGoal} />;
}
