/** Four finishing-run answers from Grafana MCP (English, not a Grafana clone). */
import { cost } from "@/lib/formatters";
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
          Run pulse
        </h2>
        <p className="mt-2 text-sm text-ink-muted">{errorMessage}</p>
      </section>
    );
  }

  if (!pulse) {
    return null;
  }

  const wheelPreview = pulse.wheel.items.slice(0, 4);
  const extra = pulse.wheel.items.length - wheelPreview.length;

  return (
    <section
      aria-labelledby="run-pulse-heading"
      className="mb-5 rounded-md border border-line bg-surface-1"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h2
          id="run-pulse-heading"
          className="font-mono text-xs uppercase tracking-widest text-ink-muted"
        >
          Run pulse
        </h2>
        <p className="font-mono text-xs uppercase tracking-wider text-ink-muted">
          Grafana {pulse.grafana}
        </p>
      </header>
      <dl className="grid gap-0 sm:grid-cols-2">
        <div className="border-b border-line px-4 py-3 sm:border-r">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            Factory or footage
          </dt>
          <dd className={`mt-1 text-sm ${verdictClass(pulse.factory.verdict)}`}>
            {pulse.factory.headline}
          </dd>
          <EvidenceLink href={pulse.factory.evidence_url} />
        </div>
        <div className="border-b border-line px-4 py-3">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            Burn you can change
          </dt>
          <dd className="mt-1 text-sm text-ink">{pulse.burn.headline}</dd>
          {pulse.burn.top[0] ? (
            <p className="mt-1 font-mono text-xs tabular-nums text-tungsten">
              {cost(pulse.burn.top[0].cost_micros)}
              {onJumpToJob && pulse.burn.top[0].job_id ? (
                <button
                  type="button"
                  onClick={() => onJumpToJob(pulse.burn.top[0].job_id)}
                  className="ml-3 uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                >
                  {pulse.burn.top[0].job_id}
                </button>
              ) : null}
            </p>
          ) : null}
          <EvidenceLink href={pulse.burn.evidence_url} />
        </div>
        <div className="px-4 py-3 sm:border-r sm:border-b-0 border-b border-line">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            When wrap
          </dt>
          <dd className="mt-1 text-sm text-ink">{pulse.eta.headline}</dd>
          <EvidenceLink href={pulse.eta.evidence_url} />
        </div>
        <div className="px-4 py-3">
          <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            Grabbed the wheel
          </dt>
          <dd className="mt-1">
            {wheelPreview.length === 0 ? (
              <p className="text-sm text-ink-muted">
                No agent interventions recorded for this dump.
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
