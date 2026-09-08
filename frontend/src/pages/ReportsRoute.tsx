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
        Checking the latest results…
      </p>
    );
  }

  if (backend === "down") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Run reports</h1>
        <EmptyState
          glyph="☾"
          title="Reports are unavailable"
          body="The service is unavailable, so the latest report cannot be loaded."
        />
      </section>
    );
  }

  if (!selectedProjectId) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Run reports</h1>
        <EmptyState
          glyph="☾"
          title="No project selected"
          body="Select a project on the timeline first. Reports are shown for one project at a time."
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
        Loading report…
      </p>
    );
  }

  const report = query.isError ? null : (query.data ?? null);
  const verdicts = report?.verdicts ?? [];
  const completedVerdicts = new Set(["pass", "passed", "healthy", "locked", "completed", "executed"]);
  const failedVerdicts = new Set(["fail", "failed", "failing"]);
  const completed = verdicts.filter((item) => completedVerdicts.has(item.verdict)).length;
  const failed = verdicts.filter((item) => failedVerdicts.has(item.verdict)).length;
  const totalCost = verdicts.reduce((sum, item) => sum + (item.cost_micros ?? 0), 0);
  const happened = verdicts.filter((item) => completedVerdicts.has(item.verdict));
  const needsAttention = verdicts.filter((item) => !completedVerdicts.has(item.verdict));
  const attention = needsAttention.filter((item) => !failedVerdicts.has(item.verdict)).length;

  if (!report || verdicts.length === 0) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Run reports</h1>
        <EmptyState
          glyph="☾"
          title="No report yet"
          body="A report will appear here after Martini Shot has completed work. It will show results, attention items, and cost."
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-3xl space-y-4 px-6 py-8">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">Run report</p>
        <h1 className="mt-1 text-2xl text-ink">Report for {report.date}</h1>
        <p className="mt-2 font-mono text-xs text-ink-muted">
          Updated {relativeTime(report.generated_at)}
        </p>
      </header>
      <section className="grid grid-cols-2 border border-line bg-surface-1 sm:grid-cols-4" aria-label="Morning report totals">
        {[
          ["Completed", completed, "text-signal"],
          ["Failed", failed, failed ? "text-danger" : "text-ink-muted"],
          ["Attention", attention, attention ? "text-tungsten" : "text-ink-muted"],
          ["Cost", cost(totalCost), "text-ink"],
        ].map(([label, value, tone]) => <div key={String(label)} className="border-b border-line px-4 py-3 last:border-0 sm:border-b-0 sm:border-r"><p className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">{label}</p><p className={`mt-1 font-mono text-lg tabular-nums ${tone}`}>{value}</p></div>)}
      </section>
      <section className="border border-line bg-surface-1 p-4">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink">Completed work</h2>
        {happened.length === 0 ? <p className="mt-2 text-sm text-ink-muted">No completed work was recorded.</p> : <div className="mt-3 space-y-3">{happened.map((verdict, index) => <VerdictRow key={`done-${verdict.station}-${index}`} verdict={verdict} />)}</div>}
      </section>
      <section className="border border-line bg-surface-1 p-4">
        <h2 className="font-mono text-xs uppercase tracking-widest text-tungsten">Needs your attention</h2>
        {needsAttention.length === 0 ? <p className="mt-2 text-sm text-ink-muted">No items need your attention.</p> : <div className="mt-3 space-y-3">{needsAttention.map((verdict, index) => <VerdictRow key={`attention-${verdict.station}-${index}`} verdict={verdict} />)}</div>}
      </section>
    </section>
  );
}
