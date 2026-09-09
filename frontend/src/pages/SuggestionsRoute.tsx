import { useQuery } from "@tanstack/react-query";

import { getWorklist } from "@/api/endpoints";
import EmptyState from "@/components/EmptyState";
import { isNotFound } from "@/lib/errors";
import { cost } from "@/lib/formatters";
import { stationName } from "@/lib/stations";
import { buildSuggestionPlan, type RankedSuggestion } from "@/lib/suggestionPlan";
import type { BackendReach, InspectNote, Worklist } from "@/types/api";

interface SuggestionsRouteProps {
  backend: BackendReach;
  selectedProjectId: string | null;
}

function impactLabel(impact: InspectNote["impact"]): string {
  if (impact === "none") return "";
  return ` · ${impact} impact`;
}

function RankedRow({
  row,
  faded,
  fitLabel,
}: {
  row: RankedSuggestion;
  faded: boolean;
  fitLabel: string;
}) {
  const spentDiffers =
    row.actualMicros != null && row.actualMicros !== row.estimateMicros;
  return (
    <li
      className={
        faded
          ? "border-b border-line px-5 py-4 opacity-50 last:border-0"
          : "border-b border-line px-5 py-4"
      }
    >
      <div className="flex gap-3">
        <span className="font-mono text-xs text-tungsten">
          {String(row.rank).padStart(2, "0")}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-mono text-xs uppercase text-ink">
              {stationName(row.item.station)}
            </span>
            <span className="font-mono text-xs tabular-nums text-ink-muted">
              {spentDiffers
                ? `${cost(row.actualMicros ?? 0)} spent · est ${cost(row.estimateMicros)}`
                : cost(row.estimateMicros)}
            </span>
          </div>
          {row.item.summary ? (
            <p className="mt-1 text-sm text-ink-muted">{row.item.summary}</p>
          ) : null}
          <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            {fitLabel}
          </p>
        </div>
      </div>
    </li>
  );
}

export default function SuggestionsRoute({
  backend,
  selectedProjectId,
}: SuggestionsRouteProps) {
  const worklistQuery = useQuery({
    queryKey: ["worklist", selectedProjectId],
    queryFn: () => getWorklist(selectedProjectId ?? ""),
    enabled: backend === "up" && selectedProjectId !== null,
    retry: false,
  });
  const worklist: Worklist | null = worklistQuery.data ?? null;
  const plan = buildSuggestionPlan(worklist);

  if (backend === "checking") {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Checking suggestions…
      </p>
    );
  }

  if (backend === "down") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Suggestions</h1>
        <EmptyState
          glyph="☰"
          title="Suggestions are unavailable"
          body="The service is unavailable, so leftover station suggestions cannot be loaded."
        />
      </section>
    );
  }

  if (!selectedProjectId) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Suggestions</h1>
        <EmptyState
          glyph="☰"
          title="No project selected"
          body="Select a project on the timeline first. Suggestions are shown for one project at a time."
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-4 px-6 py-8" aria-labelledby="suggestions-heading">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">Suggestions</p>
        <h1 id="suggestions-heading" className="mt-1 text-2xl text-ink">
          What leftover stations still want
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted">
          After ingest, mix, and pickups, specialist stations look at the updated clips.
          Martini Shot then ranks those suggestions against the remaining budget.
        </p>
        {worklist ? (
          <p className="mt-3 font-mono text-xs tabular-nums text-ink-muted">
            {cost(plan.spentMicros)} spent / {cost(plan.budgetMicros)} budget
            {plan.stage === "ranked" ? ` · ${cost(plan.remainingMicros)} left` : ""}
          </p>
        ) : null}
      </header>

      {worklistQuery.isError && !isNotFound(worklistQuery.error) ? (
        <p className="border-l-2 border-danger pl-3 text-sm text-danger">
          Suggestions could not be loaded. Check the connection and try again.
        </p>
      ) : null}

      {plan.stage === "too_early" ? (
        <EmptyState
          glyph="☰"
          title="Not yet"
          body="Suggestions appear after ingest, mix, and pickups. Specialist stations then look at the updated clips."
        />
      ) : null}

      {plan.stage === "collecting" ? (
        <article className="border border-line bg-surface-1">
          <header className="border-b border-line px-5 py-4">
            <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
              Incoming suggestions
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Stations are looking at the updated clips. This list grows as each station reports.
            </p>
          </header>
          {plan.incoming.length === 0 ? (
            <p className="px-5 py-6 text-sm text-ink-muted">No leftover suggestions yet.</p>
          ) : (
            <ul className="divide-y divide-line">
              {plan.incoming.map((row, index) => (
                <li key={`${row.station}-${row.shot_id ?? "project"}-${index}`} className="px-5 py-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-3">
                    <span className="font-mono text-xs uppercase text-ink">{stationName(row.station)}</span>
                    <span className="font-mono text-xs tabular-nums text-tungsten">
                      {cost(row.cost_estimate_micros)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-ink-muted">
                    {row.summary}
                    {impactLabel(row.impact)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </article>
      ) : null}

      {plan.stage === "ranked" ? (
        <article className="border border-line bg-surface-1">
          <header className="border-b border-line px-5 py-4">
            <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Ranked plan</h2>
            <p className="mt-1 text-sm text-ink-muted">
              {plan.cutoffAfterRank === null
                ? "All ranked work fits the remaining budget."
                : "Stack rank is the order Martini Shot will run. The cutoff moves if a step costs more than planned."}
            </p>
            {worklist?.rank_reason ? (
              <p className="mt-3 max-w-3xl border-l-2 border-agent px-3 text-sm text-ink">
                {worklist.rank_reason}
              </p>
            ) : null}
          </header>
          <ol>
            {plan.ranked
              .filter((row) => row.fit === "in_budget")
              .map((row) => (
                <RankedRow key={row.item.id} row={row} faded={false} fitLabel="Fits the envelope" />
              ))}
            {plan.cutoffAfterRank !== null ? (
              <li className="border-y border-dashed border-tungsten bg-surface-2 px-5 py-3 font-mono text-[10px] uppercase tracking-wider text-tungsten">
                Estimated cutoff — work below this line waits until the envelope has room.
              </li>
            ) : null}
            {plan.ranked
              .filter((row) => row.fit === "below_cutoff")
              .map((row) => (
                <RankedRow key={row.item.id} row={row} faded fitLabel="Below cutoff" />
              ))}
          </ol>
        </article>
      ) : null}
    </section>
  );
}
