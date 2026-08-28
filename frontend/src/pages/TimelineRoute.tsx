import EmptyState from "@/components/EmptyState";
import { STATUS_META } from "@/lib/status";
import type { JobStatus } from "@/types/api";

/** Demo-beat order: exceptions surface first (charter: exception-first). */
const BOARD_ORDER: JobStatus[] = [
  "running",
  "needs_human",
  "fail",
  "quarantined",
  "throttled",
  "pass",
  "queued",
];

/** Season timeline landing. Live lanes arrive with the backend; the legend is real content. */
export default function TimelineRoute() {
  return (
    <section aria-labelledby="timeline-heading" className="mx-auto max-w-3xl px-6 py-10">
      <h1 id="timeline-heading" className="sr-only">
        Season timeline
      </h1>

      <EmptyState
        glyph="▤"
        title="The board is dark"
        body="Stations report here once the backend streams job events. An empty board means no jobs yet — nothing on this screen is simulated."
      />

      <section className="mx-auto mt-12 max-w-xl">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">
          Reading the board
        </h2>
        <dl className="mt-3 space-y-1.5">
          {BOARD_ORDER.map((status) => {
            const meta = STATUS_META[status];
            return (
              <div key={status} className="flex items-baseline gap-3 text-sm">
                <dt className={`w-44 shrink-0 font-mono ${meta.textClass}`}>
                  <span aria-hidden className="mr-2">
                    {meta.glyph}
                  </span>
                  {meta.term}
                </dt>
                <dd className="text-ink-muted">{meta.hint}</dd>
              </div>
            );
          })}
        </dl>
      </section>
    </section>
  );
}
