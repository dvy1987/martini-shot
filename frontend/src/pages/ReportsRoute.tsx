import EmptyState from "@/components/EmptyState";

/** Dailies: the morning report lands after the overnight batch completes. */
export default function ReportsRoute() {
  return (
    <section aria-labelledby="reports-heading" className="mx-auto max-w-3xl px-6 py-10">
      <h1 id="reports-heading" className="sr-only">
        Morning reports
      </h1>
      <EmptyState
        glyph="☾"
        title="No morning report yet"
        body="After the overnight batch, the daily wrap-up lands here: per-station verdicts, cost accounting, and what the agent fixed while you slept."
      />
    </section>
  );
}
