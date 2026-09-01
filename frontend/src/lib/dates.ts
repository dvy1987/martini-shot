/** UTC calendar day for morning-report queries (ISO-8601 date). */

export function utcDateStamp(date: Date): string {
  return date.toISOString().slice(0, 10);
}
