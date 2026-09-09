/** Four finishing-run answers from Grafana MCP (English, not a Grafana clone). */
import { cost } from "@/lib/formatters";
import { stationName } from "@/lib/stations";
import { statusMetaOrUnknown } from "@/lib/status";
import type { RunPulse } from "@/types/api";

interface RunPulseProps {
  pulse: RunPulse | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  onJumpToJob?: (jobId: string) => void;
}

function verdictClass(verdict: string): string {
  if (verdict === "healthy") return "text-signal";
  if (verdict === "degraded") return "text-tungsten";
  return "text-ink-muted";
}

function EvidenceLink({ href }: { href?: string }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-mono text-[10px] uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
    >
      Grafana
    </a>
  );
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
        aria-label="Loading run pulse"
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
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">
          Grafana watch
        </h2>
        <p className="mt-2 text-sm text-ink-muted">{errorMessage}</p>
      </section>
    );
  }

  if (!pulse) {
    return null;
  }

  const dashboards = pulse.dashboards ?? [];
  const wheelPreview = pulse.wheel.items.slice(0, 4);
  const extra = pulse.wheel.items.length - wheelPreview.length;

  return (
    <section
      aria-labelledby="run-pulse-heading"
      className="mb-5 rounded-md border border-line bg-surface-1"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-agent">
            Grafana
          </p>
          <h2
            id="run-pulse-heading"
            className="mt-1 font-mono text-xs uppercase tracking-widest text-ink"
          >
            Grafana watch
          </h2>
        </div>
        <p className="font-mono text-xs uppercase tracking-wider text-ink-muted">
          {pulse.grafana === "ok" ? "Live from Grafana Cloud" : "Grafana unreachable"}
        </p>
      </header>
      {dashboards.length > 0 ? (
        <p className="flex flex-wrap gap-x-4 gap-y-1 border-b border-line px-4 py-2 font-mono text-[10px] uppercase tracking-wider">
          {dashboards.map((dashboard) => (
            <a
              key={dashboard.url}
              href={dashboard.url}
              target="_blank"
              rel="noreferrer"
              className="text-agent underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              {dashboard.title}
            </a>
          ))}
        </p>
      ) : null}
      <div className="border-b border-line px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Jobs this run</p>
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
      <dl className="grid gap-0 sm:grid-cols-2">
        <div className="border-b border-line px-4 py-3 sm:border-r">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            System and media health
          </dt>
          <dd className={`mt-1 text-sm ${verdictClass(pulse.factory.verdict)}`}>
            {pulse.factory.headline}
          </dd>
          <EvidenceLink href={pulse.factory.evidence_url} />
        </div>
        <div className="border-b border-line px-4 py-3">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            Cost to run
          </dt>
          <dd className="mt-1 text-sm text-ink">{pulse.burn.headline}</dd>
          {pulse.burn.top[0] ? (
            (() => {
              const topJob = pulse.burn.top[0];
              if (!topJob) return null;
              return (
            <p className="mt-1 font-mono text-xs tabular-nums text-tungsten">
              {cost(topJob.cost_micros)}
              {onJumpToJob && topJob.job_id ? (
                <button
                  type="button"
                  onClick={() => onJumpToJob(topJob.job_id)}
                  className="ml-3 uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                >
                  {topJob.job_id}
                </button>
              ) : null}
            </p>
              );
            })()
          ) : null}
          <EvidenceLink href={pulse.burn.evidence_url} />
        </div>
        <div className="px-4 py-3 sm:border-r sm:border-b-0 border-b border-line">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            Expected finish
          </dt>
          <dd className="mt-1 text-sm text-ink">{pulse.eta.headline}</dd>
          <EvidenceLink href={pulse.eta.evidence_url} />
        </div>
        <div className="px-4 py-3">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            Automatic actions
          </dt>
          <dd className="mt-1">
            {wheelPreview.length === 0 ? (
              <p className="text-sm text-ink-muted">
                No automatic actions recorded for this run.
              </p>
            ) : (
              <ul className="space-y-1">
                {wheelPreview.map((item, index) => (
                  <li key={`${item.kind}-${item.at}-${index}`} className="line-clamp-2 text-sm text-ink">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-agent">
                      {item.kind}
                    </span>{" "}
                    {item.text}
                  </li>
                ))}
              </ul>
            )}
            {extra > 0 ? (
              <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                +{extra} more
              </p>
            ) : null}
          </dd>
        </div>
      </dl>
    </section>
  );
}
