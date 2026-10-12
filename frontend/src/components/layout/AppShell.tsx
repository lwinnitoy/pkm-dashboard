import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useFinance } from "../../data/financeContext";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

export default function AppShell() {
  const { message, error, loaded, refresh } = useFinance();
  const location = useLocation();

  // A bank's OAuth page returns to PLAID_REDIRECT_URI (the site root) with
  // ?oauth_state_id. Only the Accounts page has the Link button that finishes the
  // flow, so forward the return there, query string and all.
  if (location.search.includes("oauth_state_id") && location.pathname !== "/accounts") {
    return <Navigate to={`/accounts${location.search}`} replace />;
  }

  let content = <Outlet />;
  if (!loaded) {
    // Before the first successful load, pages would render empty data as real
    // zeros, so show the state instead.
    content = error ? (
      <div className="card">
        <p className="muted">Couldn't load your data.</p>
        <button className="btn" onClick={() => refresh()}>
          Retry
        </button>
      </div>
    ) : (
      <p className="muted">Loading…</p>
    );
  }

  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <Topbar />
        <div className="page">
          {error && (
            <div className="banner error" role="alert">
              {error}
            </div>
          )}
          {message && (
            <div className="banner" role="status">
              {message}
            </div>
          )}
          {content}
        </div>
      </div>
    </div>
  );
}
