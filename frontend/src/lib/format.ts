// Shared formatting helpers so currency/percent/date rendering is consistent
// across every page.
import { parseDate } from "./dates";

/** Amounts are shown in this currency unless a row says otherwise. Totals across
 * accounts are summed as-is: there's no FX conversion, so a US$ account counts
 * at face value. */
export const HOME_CURRENCY = "CAD";

const formatters = new Map<string, Intl.NumberFormat>();

/** en-CA formatting: "$1,234.56" for CAD, "US$12.00" for anything foreign, so a
 * row in another currency is never mistaken for a home-currency one. */
function fmt(code: string | null | undefined, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const cur = (code || HOME_CURRENCY).toUpperCase();
  const key = `${cur}|${JSON.stringify(options)}`;
  let f = formatters.get(key);
  if (!f) {
    try {
      f = new Intl.NumberFormat("en-CA", { style: "currency", currency: cur, ...options });
    } catch {
      // An unknown code from upstream data: fall back rather than throw mid-render.
      f = new Intl.NumberFormat("en-CA", { style: "currency", currency: HOME_CURRENCY, ...options });
    }
    formatters.set(key, f);
  }
  return f;
}

/** $1,234.56 (or US$1,234.56 when `code` isn't the home currency) */
export function currency(n: number | null | undefined, code?: string | null): string {
  if (n == null) return "—";
  return fmt(code, { maximumFractionDigits: 2 }).format(n);
}

/** $1,235 (no cents) — for large headline numbers */
export function currencyWhole(n: number | null | undefined, code?: string | null): string {
  if (n == null) return "—";
  return fmt(code, { maximumFractionDigits: 0 }).format(n);
}

/** $1.2K / $3.4M / -$1.2K — for chart axes and dense tables */
export function currencyCompact(n: number | null | undefined, code?: string | null): string {
  if (n == null) return "—";
  return fmt(code, { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

/** 12.3% with an explicit sign */
export function percent(n: number | null | undefined, signed = false): string {
  if (n == null) return "—";
  const sign = signed && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

/** Aug 31 */
export function shortDate(iso: string): string {
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Aug 31, 2026 */
export function longDate(iso: string): string {
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
