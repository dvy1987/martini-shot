import { useQuery } from "@tanstack/react-query";

import { getRunPulse, getWorklist } from "@/api/endpoints";
import EmptyState from "@/components/EmptyState";
import RunPulseStrip from "@/components/RunPulse";
import type { BackendReach } from "@/types/api";

interface AnalyticsRouteProps {
  backend: BackendReach;
  selectedProjectId: string | null;
  onJumpToJob?: (jobId: string) => void;
}

export default function AnalyticsRoute({
  backend,
  selectedProjectId,
  onJumpToJob,
}: AnalyticsRouteProps) {
  const worklistQuery = useQuery({
    queryKey: ["worklist", selectedProjectId],
    queryFn: () => getWorklist(selectedProjectId ?? ""),
    enabled: backend === "up" && selectedProjectId !== null,
    retry: false,
  });
  const worklistStatus = worklistQuery.data?.status ?? "";
  const worklistHasActiveItems = Boolean(
    worklistQuery.data?.items?.some((item) =>
      ["queued", "leased", "running"].includes(item.status),
    ),
  );
  const turnoverActive =
    worklistHasActiveItems ||
    worklistStatus === "running" ||
    worklistStatus === "waiting_for_ingest" ||
    worklistStatus === "inspecting";
  const pulseQuery = useQuery({
    queryKey: ["run-pulse", selectedProjectId],
    queryFn: () => getRunPulse(selectedProjectId ?? ""),
    enabled: backend === "up" && selectedProjectId !== null,
    retry: false,
    refetchInterval: turnoverActive ? 15_000 : false,
  });

  if (backend === "checking") {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Checking Grafana watch…
      </p>
    );
  }

  if (backend === "down") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Analytics</h1>
        <EmptyState
          glyph="▣"
          title="Analytics are unavailable"
          body="The service is unavailable, so Grafana watch cannot be loaded."
        />
      </section>
    );
  }

  if (!selectedProjectId) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Analytics</h1>
        <EmptyState
          glyph="▣"
          title="No project selected"
          body="Select a project on the timeline first. Analytics are shown for one project at a time."
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-4 px-6 py-8" aria-labelledby="analytics-heading">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">Analytics</p>
        <h1 id="analytics-heading" className="mt-1 text-2xl text-ink">
          Grafana watch
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted">
          Factory health, cost, finish time, and automatic actions for this run — sourced from Grafana.
        </p>
      </header>
      <RunPulseStrip
        pulse={pulseQuery.data ?? null}
        isLoading={pulseQuery.isPending}
        errorMessage={
          pulseQuery.isError
            ? "Grafana watch could not be loaded. Check the connection and try again."
            : null
        }
        onJumpToJob={onJumpToJob}
      />
    </section>
  );
}
