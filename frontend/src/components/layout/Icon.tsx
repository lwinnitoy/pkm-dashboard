// Inline line-icons for the sidebar (no icon dependency).
const PATHS: Record<string, React.ReactNode> = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  cashflow: (
    <>
      <path d="M7 21V6M7 6 4 9M7 6l3 3" />
      <path d="M17 3v15M17 18l3-3M17 18l-3-3" />
    </>
  ),
  transactions: <path d="M4 7h16M4 12h16M4 17h10" />,
  budgets: (
    <>
      <rect x="3" y="5" width="14" height="3" rx="1.5" />
      <rect x="3" y="10.5" width="18" height="3" rx="1.5" />
      <rect x="3" y="16" width="9" height="3" rx="1.5" />
    </>
  ),
  investments: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 3.5V12h8.5" />
    </>
  ),
  networth: (
    <>
      <path d="M4 15l5-5 4 4 7-7" />
      <path d="M16 7h4v4" />
    </>
  ),
  goals: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <circle cx="12" cy="12" r="0.8" fill="currentColor" />
    </>
  ),
  accounts: (
    <>
      <rect x="3" y="6" width="18" height="13" rx="2.5" />
      <path d="M3 10h18M16 15h2" />
    </>
  ),
  import: (
    <>
      <path d="M12 3v11" />
      <path d="M8 10l4 4 4-4" />
      <path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
    </>
  ),
};

export function Icon({ name }: { name: string }) {
  return (
    <svg
      className="nav-ico"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      width="18"
      height="18"
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}
