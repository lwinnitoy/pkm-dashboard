import { Outlet } from "react-router-dom";
import { useFinance } from "../../data/financeContext";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

export default function AppShell() {
  const { message, error } = useFinance();
  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <Topbar />
        <div className="page">
          {error && <div className="banner error">{error}</div>}
          {message && <div className="banner">{message}</div>}
          <Outlet />
        </div>
      </div>
    </div>
  );
}
