import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./App.css";
import AppShell from "./components/layout/AppShell";
import { FinanceProvider } from "./data/FinanceProvider";
import Accounts from "./pages/Accounts";
import CashFlow from "./pages/CashFlow";
import Goals from "./pages/Goals";
import Investments from "./pages/Investments";
import NetWorth from "./pages/NetWorth";
import Overview from "./pages/Overview";
import Transactions from "./pages/Transactions";

export default function App() {
  return (
    <BrowserRouter>
      <FinanceProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Overview />} />
            <Route path="cash-flow" element={<CashFlow />} />
            <Route path="transactions" element={<Transactions />} />
            <Route path="investments" element={<Investments />} />
            <Route path="net-worth" element={<NetWorth />} />
            <Route path="goals" element={<Goals />} />
            <Route path="accounts" element={<Accounts />} />
          </Route>
        </Routes>
      </FinanceProvider>
    </BrowserRouter>
  );
}
