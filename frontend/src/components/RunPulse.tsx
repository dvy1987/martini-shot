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
        className="mb-5 rounded-md border border-line bg-surface-1 px-4 py-3"
      >
        <div className="h-3 w-24 rounded-sm bg-surface-2" />
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="h-12 rounded-sm bg-surface-2" />
          <div className="h-12 rounded-sm bg-surface-2" />
        </div>
      </section>
    );
  }

  if (errorMessage && !pulse) {
    return (
      <section className="mb-5 rounded-md border border-line bg-surface-1 px-4 py-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">This run</h2>
        <p className="mt-2 text-sm text-ink-muted">{errorMessage}</p>
      </section>
    );
  }

  if (!pulse) {
    return null;
  }

  const briefing = buildRunBriefing(pulse);

  return (
    <section aria-labelledby="run-pulse-heading" className="mb-5 rounded-md border border-line bg-surface-1">
      <header className="border-b border-line px-4 py-3">
        <h2 id="run-pulse-heading" className="sr-only">
          {briefing.title}
        </h2>
        <p className="text-sm text-ink-muted">{briefing.sourceLine}</p>
      </header>
      <dl className="grid gap-0 sm:grid-cols-2">
        {briefing.sections.map((section) => (
          <div
            key={section.id}
            className="border-b border-line px-4 py-3 sm:odd:border-r"
          >
            <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">{section.title}</dt>
            <dd className={`mt-1 text-sm ${toneClass(section.tone)}`}>{section.meaning}</dd>
            <p className="mt-1 text-sm text-ink">{section.detail}</p>
            {section.id === "spend" && pulse.burn.top[0] && onJumpToJob ? (
              <button
                type="button"
                onClick={() => onJumpToJob(pulse.burn.top[0]?.job_id ?? "")}
                className="mt-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                Open the expensive job
              </button>
            ) : null}
          </div>
        ))}
      </dl>
      {briefing.actions.length > 0 ? (
        <div className="border-t border-line px-4 py-3">
          <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Automatic actions</h3>
          <ul className="mt-2 space-y-2">
            {briefing.actions.map((item, index) => (
              <li key={`${item.kind}-${item.jobId ?? index}`} className="text-sm text-ink">
                <p>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-agent">{item.label}</span>{" "}
                  {item.text}
                </p>
                {item.jobId && onJumpToJob ? (
                  <button
                    type="button"
                    onClick={() => onJumpToJob(item.jobId ?? "")}
                    className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                  >
                    Open on Timeline
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="border-t border-line px-4 py-3">
        <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Jobs this run</h3>
        {(pulse.jobs ?? []).length === 0 ? (
          <p className="mt-2 text-sm text-ink-muted">No jobs on this project yet.</p>
        ) : (
          <ul className="mt-2 space-y-1">
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
                      className="flex w-full items-baseline justify-between gap-3 text-left text-sm text-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
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
                    <p className="flex items-baseline justify-between gap-3 text-sm text-ink">
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
