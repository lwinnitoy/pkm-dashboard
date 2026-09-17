// Navigation config shared by the sidebar and topbar.
export const NAV = [
  { to: "/", label: "Overview", icon: "overview", end: true },
  { to: "/cash-flow", label: "Cash Flow", icon: "cashflow", end: false },
  { to: "/budgets", label: "Budgets", icon: "budgets", end: false },
  { to: "/transactions", label: "Transactions", icon: "transactions", end: false },
  { to: "/investments", label: "Investments", icon: "investments", end: false },
  { to: "/net-worth", label: "Net Worth", icon: "networth", end: false },
  { to: "/goals", label: "Goals", icon: "goals", end: false },
  { to: "/accounts", label: "Accounts", icon: "accounts", end: false },
  { to: "/import", label: "Import", icon: "import", end: false },
] as const;
