import { useLocation } from "react-router-dom";
import { useFinance } from "../../data/financeContext";
import { RANGE_OPTIONS } from "../../data/financeContext";
import PlaidLinkButton from "../PlaidLinkButton";
import { NAV } from "./nav";

function useTitle(): string {
  const { pathname } = useLocation();
  const match = NAV.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
  return match?.label ?? "Finances";
}

export default function Topbar() {
  const title = useTitle();
  const { range, setRange, sync, syncing, refresh } = useFinance();

  return (
    <header className="topbar">
      <div className="topbar-title">{title}</div>
      <div className="topbar-actions">
        <div className="segmented">
          {RANGE_OPTIONS.map((r) => (
            <button
              key={r.days}
              className={range === r.days ? "active" : ""}
              onClick={() => setRange(r.days)}
            >
              {r.label}
            </button>
          ))}
        </div>
        <PlaidLinkButton onLinked={refresh} />
        <button className="btn" onClick={sync} disabled={syncing}>
          {syncing ? "Syncing…" : "Sync now"}
        </button>
      </div>
    </header>
  );
}
