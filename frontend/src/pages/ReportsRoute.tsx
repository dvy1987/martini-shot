import { useQuery } from "@tanstack/react-query";

import { getMorningReport } from "@/api/endpoints";
import CaseNote from "@/components/CaseNote";
import EmptyState from "@/components/EmptyState";
import { utcDateStamp } from "@/lib/dates";
import { asApiError, isNotFound } from "@/lib/errors";
import { cost, relativeTime } from "@/lib/formatters";
import { statusMetaFor } from "@/lib/status";
import type { BackendReach, ReportVerdict } from "@/types/api";

interface ReportsRouteProps {
  backend: BackendReach;
  selectedProjectId: string | null;
}

function VerdictRow({ verdict }: { verdict: ReportVerdict }) {
  const meta = statusMetaFor(verdict.verdict);

  return (
    <article className="rounded-md border border-line bg-surface-2 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink">
          {verdict.station.replaceAll("_", " ")}
        </h2>
        {meta ? (
          <p className={`font-mono text-xs ${meta.textClass}`}>
            <span aria-hidden className="mr-2">
              {meta.glyph}
            </span>
            {meta.term}
          </p>
        ) : (
          <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">
            {verdict.verdict}
          </p>
        )}
      </div>
      <p className="mt-2 text-sm text-ink-muted">{verdict.summary}</p>
      <div className="mt-3 flex flex-wrap items-center gap-4 font-mono text-xs text-ink-muted">
        {verdict.cost_micros != null ? (
          <span className="tabular-nums text-tungsten">{cost(verdict.cost_micros)}</span>
        ) : null}
        {verdict.evidence_url ? (
          <a
            href={verdict.evidence_url}
            className="uppercase tracking-wider text-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Evidence
          </a>
        ) : null}
      </div>
    </article>
  );
}

export default function ReportsRoute({ backend, selectedProjectId }: ReportsRouteProps) {
  const date = utcDateStamp(new Date());
  const query = useQuery({
    queryKey: ["morning-report", selectedProjectId, date],
    queryFn: () => getMorningReport(selectedProjectId ?? "", date),
    enabled: backend === "up" && selectedProjectId !== null,
    retry: false,
  });

  if (backend === "checking") {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Checking dailies…
      </p>
    );
  }

  if (backend === "down") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Morning reports</h1>
        <EmptyState
          glyph="☾"
          title="Dailies are unreachable"
          body="The backend is offline, so there is no morning report to show. Nothing on this page is simulated."
        />
      </section>
    );
  }

  if (!selectedProjectId) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Morning reports</h1>
        <EmptyState
          glyph="☾"
          title="No project selected"
          body="Pick a season on the timeline first. Dailies are per project, and this screen will not invent one."
        />
      </section>
    );
  }

  if (query.isError && !isNotFound(query.error)) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <CaseNote error={asApiError(query.error)} onRetry={() => void query.refetch()} />
      </section>
    );
  }

  if (query.isPending) {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Loading morning report…
      </p>
    );
  }

  const report = query.isError ? null : (query.data ?? null);
  const verdicts = report?.verdicts ?? [];

  if (!report || verdicts.length === 0) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Morning reports</h1>
        <EmptyState
          glyph="☾"
          title="No morning report yet"
          body="After the overnight batch, the daily wrap-up lands here: per-station verdicts, cost accounting, and what the agent fixed while you slept."
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-3xl space-y-4 px-6 py-8">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">Dailies</p>
        <h1 className="mt-1 text-2xl text-ink">Morning report · {report.date}</h1>
        <p className="mt-2 font-mono text-xs text-ink-muted">
          Generated {relativeTime(report.generated_at)}
        </p>
      </header>
      {verdicts.map((verdict, index) => (
        <VerdictRow key={`${verdict.station}-${index}`} verdict={verdict} />
      ))}
    </section>
  );
}
