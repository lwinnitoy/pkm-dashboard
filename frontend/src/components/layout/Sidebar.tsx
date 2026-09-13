import { NavLink } from "react-router-dom";
import { Icon } from "./Icon";
import { NAV } from "./nav";

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-logo" />
        Finances
      </div>

      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
        >
          <Icon name={item.icon} />
          {item.label}
        </NavLink>
      ))}

      <div className="sidebar-spacer" />
      <div className="sidebar-foot">Self-hosted · Plaid</div>
    </aside>
  );
}
