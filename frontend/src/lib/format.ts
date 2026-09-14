// Shared formatting helpers so currency/percent/date rendering is consistent
// across every page.

const currencyFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const currencyWholeFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const compactFmt = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** $1,234.56 */
export function currency(n: number | null | undefined): string {
  if (n == null) return "—";
  return currencyFmt.format(n);
}

/** $1,235 (no cents) — for large headline numbers */
export function currencyWhole(n: number | null | undefined): string {
  if (n == null) return "—";
  return currencyWholeFmt.format(n);
}

/** $1.2K / $3.4M — for chart axes and dense tables */
export function currencyCompact(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${compactFmt.format(n)}`;
}

/** 12.3% with an explicit sign */
export function percent(n: number | null | undefined, signed = false): string {
  if (n == null) return "—";
  const sign = signed && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

/** Aug 31 */
export function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Aug 31, 2026 */
export function longDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
