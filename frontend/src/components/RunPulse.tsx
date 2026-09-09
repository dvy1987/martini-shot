/** This-run briefing: health, spend, time left, automatic actions — in the product. */
import { buildRunBriefing } from "@/lib/runBriefing";
import { stationName } from "@/lib/stations";
import { statusMetaOrUnknown } from "@/lib/status";
import type { RunPulse } from "@/types/api";

interface RunPulseProps {
  pulse: RunPulse | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  onJumpToJob?: (jobId: string) => void;
}

function toneClass(tone: "ok" | "warn" | "muted"): string {
  if (tone === "ok") return "text-signal";
  if (tone === "warn") return "text-tungsten";
  return "text-ink-muted";
}

export default function RunPulseStrip({
  pulse,
  isLoading = false,
  errorMessage = null,
  onJumpToJob,
}: RunPulseProps) {
  if (isLoading && !pulse) {
    return (
      <section
        aria-busy="true"
        aria-label="Loading this run"
        className="space-y-6"
      >
        <div className="h-3 w-64 rounded-sm bg-surface-2" />
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
        </div>
      </section>
    );
  }

  if (errorMessage && !pulse) {
    return (
      <section className="rounded-md border border-line bg-surface-1 px-5 py-6">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">This run</h2>
        <p className="mt-3 text-sm leading-relaxed text-ink-muted">{errorMessage}</p>
      </section>
    );
  }

  if (!pulse) {
    return null;
  }

  const briefing = buildRunBriefing(pulse);

  return (
    <section aria-labelledby="run-pulse-heading" className="space-y-8">
      <header>
        <h2 id="run-pulse-heading" className="sr-only">
          {briefing.title}
        </h2>
        <p className="max-w-2xl text-sm leading-relaxed text-ink-muted">{briefing.sourceLine}</p>
      </header>
      <div className="grid gap-6 sm:grid-cols-2">
        {briefing.sections.map((section) => (
          <article
            key={section.id}
            aria-labelledby={`pulse-${section.id}`}
            className="flex min-h-52 flex-col rounded-md border border-line bg-surface-1 px-5 py-6"
          >
            <h3
              id={`pulse-${section.id}`}
              className="font-mono text-[10px] uppercase tracking-wider text-ink-muted"
            >
              {section.title}
            </h3>
            <p className={`mt-4 text-lg leading-snug ${toneClass(section.tone)}`}>{section.meaning}</p>
            <p className="mt-4 flex-1 text-sm leading-relaxed text-ink">{section.detail}</p>
            {section.id === "spend" && pulse.burn.top[0] && onJumpToJob ? (
              <button
                type="button"
                onClick={() => onJumpToJob(pulse.burn.top[0]?.job_id ?? "")}
                className="mt-5 self-start font-mono text-[10px] uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                Open the expensive job
              </button>
            ) : null}
          </article>
        ))}
      </div>
      {briefing.actions.length > 0 ? (
        <div className="rounded-md border border-line bg-surface-1 px-5 py-6">
          <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Automatic actions</h3>
          <ul className="mt-4 space-y-4">
            {briefing.actions.map((item, index) => (
              <li key={`${item.kind}-${item.jobId ?? index}`} className="text-sm leading-relaxed text-ink">
                <p>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-agent">{item.label}</span>{" "}
                  {item.text}
                </p>
                {item.jobId && onJumpToJob ? (
                  <button
                    type="button"
                    onClick={() => onJumpToJob(item.jobId ?? "")}
                    className="mt-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                  >
                    Open on Timeline
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="rounded-md border border-line bg-surface-1 px-5 py-6">
        <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Jobs this run</h3>
        {(pulse.jobs ?? []).length === 0 ? (
          <p className="mt-4 text-sm leading-relaxed text-ink-muted">No jobs on this project yet.</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {(pulse.jobs ?? []).map((row) => {
              const meta = statusMetaOrUnknown(row.status);
              const stage = stationName(row.station);
              return (
                <li key={row.job_id}>
                  {onJumpToJob ? (
                    <button
                      type="button"
                      aria-label={`${stage} · ${row.clip}`}
                      onClick={() => onJumpToJob(row.job_id)}
                      className="flex w-full items-baseline justify-between gap-4 text-left text-sm text-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                    >
                      <span className="min-w-0 truncate">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                          {stage}
                        </span>{" "}
                        {row.clip}
                      </span>
                      <span className={`shrink-0 font-mono text-[10px] uppercase ${meta.textClass}`}>
                        {meta.term}
                      </span>
                    </button>
                  ) : (
                    <p className="flex items-baseline justify-between gap-4 text-sm text-ink">
                      <span className="min-w-0 truncate">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                          {stage}
                        </span>{" "}
                        {row.clip}
                      </span>
                      <span className={`shrink-0 font-mono text-[10px] uppercase ${meta.textClass}`}>
                        {meta.term}
                      </span>
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
