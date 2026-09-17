import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./App.css";
import AuthGate from "./components/AuthGate";
import AppShell from "./components/layout/AppShell";
import { FinanceProvider } from "./data/FinanceProvider";
import Accounts from "./pages/Accounts";
import Budgets from "./pages/Budgets";
import CashFlow from "./pages/CashFlow";
import Goals from "./pages/Goals";
import Import from "./pages/Import";
import Investments from "./pages/Investments";
import NetWorth from "./pages/NetWorth";
import Overview from "./pages/Overview";
import Transactions from "./pages/Transactions";

export default function App() {
  return (
    <BrowserRouter>
      <AuthGate>
        <FinanceProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Overview />} />
            <Route path="cash-flow" element={<CashFlow />} />
            <Route path="budgets" element={<Budgets />} />
            <Route path="transactions" element={<Transactions />} />
            <Route path="investments" element={<Investments />} />
            <Route path="net-worth" element={<NetWorth />} />
            <Route path="goals" element={<Goals />} />
            <Route path="accounts" element={<Accounts />} />
            <Route path="import" element={<Import />} />
          </Route>
        </Routes>
        </FinanceProvider>
      </AuthGate>
    </BrowserRouter>
  );
}
