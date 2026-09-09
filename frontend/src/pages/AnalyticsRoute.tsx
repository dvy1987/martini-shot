import { useQuery } from "@tanstack/react-query";

import { getRunPulse, getWorklist, listProjects } from "@/api/endpoints";
import EmptyState from "@/components/EmptyState";
import RunPulseStrip from "@/components/RunPulse";
import type { BackendReach, Job } from "@/types/api";

interface AnalyticsRouteProps {
  backend: BackendReach;
  selectedProjectId: string | null;
  jobs?: readonly Job[];
  onJumpToJob?: (jobId: string) => void;
}

export default function AnalyticsRoute({
  backend,
  selectedProjectId,
  jobs,
  onJumpToJob,
}: AnalyticsRouteProps) {
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    enabled: backend === "up",
  });
  const openProject = (projectsQuery.data ?? []).find(
    (project) => project.project_id === selectedProjectId,
  );
  const waitingForTimelineProject =
    selectedProjectId === null &&
    (projectsQuery.isPending || (projectsQuery.data?.length ?? 0) > 0);

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
        Checking this run…
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
          body="The service is unavailable, so this run cannot be loaded."
        />
      </section>
    );
  }

  if (waitingForTimelineProject) {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Opening the same project as Timeline…
      </p>
    );
  }

  if (!selectedProjectId) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Analytics</h1>
        <EmptyState
          glyph="▣"
          title="No project selected"
          body="Start a project on the timeline. Analytics uses the same show as Timeline."
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-5xl space-y-8 px-6 py-8" aria-labelledby="analytics-heading">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">Analytics</p>
        <h1 id="analytics-heading" className="mt-1 text-2xl text-ink">
          This run
        </h1>
        {openProject ? (
          <p className="mt-1 font-mono text-xs uppercase tracking-widest text-agent">{openProject.title}</p>
        ) : null}
        <p className="mt-2 max-w-2xl text-sm text-ink-muted">
          Why Execute or Delivery stopped, and what to do next — explained here for this show.
        </p>
      </header>
      <RunPulseStrip
        pulse={pulseQuery.data ?? null}
        isLoading={pulseQuery.isPending}
        liveJobs={jobs}
        worklist={worklistQuery.data ?? null}
        errorMessage={
          pulseQuery.isError
            ? "This run could not be loaded. Check the connection and try again."
            : null
        }
        onJumpToJob={onJumpToJob}
      />
    </section>
  );
}
