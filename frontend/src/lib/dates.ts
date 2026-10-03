// Calendar-date helpers. The API sends dates (transaction dates, trend buckets,
// goal targets) as bare "YYYY-MM-DD" strings, and JS parses those as *UTC*
// midnight: `new Date("2026-09-30")` is still Sep 29 anywhere west of Greenwich.
// So they're read as local calendar dates here, and "this month" comes from the
// local clock rather than the UTC one `toISOString()` reports.

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * A `YYYY-MM-DD` string as local midnight of that calendar day. Anything else
 * (a full ISO timestamp names an instant, not a day) goes through `new Date`.
 */
export function parseDate(iso: string): Date {
  const m = DATE_ONLY.exec(iso);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
}

/** `YYYY-MM-DD` of the local calendar day containing `d` (default: now). */
export function dayKey(d: Date = new Date()): string {
  return `${monthKey(d)}-${String(d.getDate()).padStart(2, "0")}`;
}

/** `YYYY-MM` of the local calendar month containing `d` (default: now). */
export function monthKey(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
