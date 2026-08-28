import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { getJob, getProject, listProjects } from "@/api/endpoints";
import EmptyState from "@/components/EmptyState";
import InvestigationDrawer, {
  type InvestigationDrawerError,
} from "@/components/InvestigationDrawer";
import TimelineBoard from "@/components/TimelineBoard";
import { STATUS_META } from "@/lib/status";
import type { JobStatus } from "@/types/api";

const BOARD_ORDER: JobStatus[] = [
  "running",
  "needs_human",
  "fail",
  "quarantined",
  "throttled",
  "pass",
  "queued",
];

interface TimelineRouteProps {
  selectedProjectId: string | null;
  onSelectedProjectIdChange: (projectId: string | null) => void;
}

function StatusLegend() {
  return (
    <section className="mt-8 rounded-md border border-line bg-surface-1 p-4">
      <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">
        Reading the board
      </h2>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        {BOARD_ORDER.map((status) => {
          const meta = STATUS_META[status];
          return (
            <div key={status} className="flex items-baseline gap-3 text-sm">
              <dt className={`w-36 shrink-0 font-mono ${meta.textClass}`}>
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
  );
}

function TimelineSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading season timeline"
      className="rounded-md border border-line bg-surface-1"
    >
      <div className="grid grid-cols-[10rem_1fr] border-b border-line bg-surface-2 px-4 py-2">
        <span className="h-3 w-16 rounded-sm bg-line" />
        <span className="h-3 w-28 rounded-sm bg-line" />
      </div>
      {[0, 1, 2, 3].map((row) => (
        <div
          key={row}
          className="grid grid-cols-[10rem_1fr] border-b border-line px-4 py-2 last:border-b-0"
        >
          <span className="my-auto h-3 w-20 rounded-sm bg-surface-2" />
          <div className="grid grid-cols-3 gap-2">
            <span className="h-16 rounded-md bg-surface-2" />
            <span className="h-16 rounded-md bg-surface-2" />
            <span className="h-16 rounded-md bg-surface-2" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function TimelineRoute({
  selectedProjectId,
  onSelectedProjectIdChange,
}: TimelineRouteProps) {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [inspectedJobId, setInspectedJobId] = useState<string | null>(null);
  const jobTriggerRef = useRef<HTMLElement | null>(null);
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const projectQuery = useQuery({
    queryKey: ["project", selectedProjectId],
    queryFn: () => getProject(selectedProjectId ?? ""),
    enabled: selectedProjectId !== null,
  });
  const jobQuery = useQuery({
    queryKey: ["job", inspectedJobId],
    queryFn: () => getJob(inspectedJobId ?? ""),
    enabled: inspectedJobId !== null,
  });

  const handleJobSelection = useCallback(
    (jobId: string, trigger: HTMLElement) => {
      jobTriggerRef.current = trigger;
      if (selectedJobId === jobId || inspectedJobId !== null) setInspectedJobId(jobId);
      setSelectedJobId(jobId);
    },
    [inspectedJobId, selectedJobId],
  );

  const closeInvestigation = useCallback(() => {
    setInspectedJobId(null);
  }, []);

  useEffect(() => {
    const projects = projectsQuery.data;
    if (!projects) return;

    if (projects.length === 0) {
      if (selectedProjectId !== null) onSelectedProjectIdChange(null);
      return;
    }

    if (!selectedProjectId || !projects.some(({ project_id }) => project_id === selectedProjectId)) {
      onSelectedProjectIdChange(projects[0]?.project_id ?? null);
    }
  }, [onSelectedProjectIdChange, projectsQuery.data, selectedProjectId]);

  useEffect(() => {
    setSelectedJobId(null);
    setInspectedJobId(null);
    jobTriggerRef.current = null;
  }, [selectedProjectId]);

  if (projectsQuery.isPending) {
    return (
      <section className="px-6 py-8">
        <TimelineSkeleton />
      </section>
    );
  }

  if (projectsQuery.isError) {
    const error =
      projectsQuery.error instanceof ApiError
        ? projectsQuery.error
        : new ApiError("network_error", "The Martini Shot API could not be reached.", 0);

    return (
      <section className="mx-auto max-w-3xl px-6 py-14">
        <EmptyState
          glyph="!"
          title="The board is unreachable"
          body={error.message}
        />
        <p className="mt-4 text-center font-mono text-xs uppercase tracking-wider text-ink-muted">
          {error.code}
        </p>
        <div className="mt-5 text-center">
          <button
            type="button"
            onClick={() => void projectsQuery.refetch()}
            className="rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted active:bg-surface-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Retry connection
          </button>
        </div>
        <StatusLegend />
      </section>
    );
  }

  if (projectsQuery.data.length === 0) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-14">
        <EmptyState
          glyph="▤"
          title="The board is dark"
          body="Stations report here once the backend streams job events. An empty board means no jobs yet — nothing on this screen is simulated."
        />
        <StatusLegend />
      </section>
    );
  }

  const selectedProject = projectsQuery.data.find(
    ({ project_id }) => project_id === selectedProjectId,
  );
  const jobs = projectQuery.data?.jobs ?? [];

  return (
    <section aria-labelledby="timeline-heading" className="px-6 py-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">
            Season timeline
          </p>
          <h1 id="timeline-heading" className="mt-1 text-2xl text-ink">
            {projectQuery.data?.title ?? selectedProject?.title ?? "Loading project"}
          </h1>
        </div>
        <label className="grid gap-1 font-mono text-xs uppercase tracking-wider text-ink-muted">
          Project
          <select
            value={selectedProjectId ?? ""}
            onChange={(event) => onSelectedProjectIdChange(event.target.value || null)}
            className="min-w-48 rounded-sm border border-line bg-surface-2 px-3 py-2 font-sans text-sm normal-case tracking-normal text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            {projectsQuery.data.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      {projectQuery.isPending || !selectedProjectId ? <TimelineSkeleton /> : null}

      {projectQuery.isError
        ? (() => {
            const error =
              projectQuery.error instanceof ApiError
                ? projectQuery.error
                : new ApiError("network_error", "The selected project could not be reached.", 0);
            return (
              <div className="rounded-md border border-line bg-surface-1 px-6 py-10 text-center">
                <p className="text-xl text-ink">This turnover could not be loaded.</p>
                <p className="mt-2 text-sm text-ink-muted">{error.message}</p>
                <p className="mt-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
                  {error.code}
                </p>
                <button
                  type="button"
                  onClick={() => void projectQuery.refetch()}
                  className="mt-5 rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted active:bg-surface-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                >
                  Retry project
                </button>
              </div>
            );
          })()
        : null}

      {projectQuery.isSuccess && jobs.length === 0 ? (
        <EmptyState
          glyph="▤"
          title="Awaiting first turnover"
          body="This project has no observed jobs yet. The timeline will populate when the API reports real station activity."
        />
      ) : null}

      {projectQuery.isSuccess && jobs.length > 0 ? (
        <TimelineBoard
          jobs={jobs}
          selectedJobId={selectedJobId}
          onSelectJob={handleJobSelection}
        />
      ) : null}

      {selectedJobId ? (
        <p className="mt-3 font-mono text-xs text-ink-muted">
          Selected clip <span className="text-ink">{selectedJobId}</span>
        </p>
      ) : null}

      <StatusLegend />

      <InvestigationDrawer
        open={inspectedJobId !== null}
        job={jobQuery.data ?? null}
        isLoading={jobQuery.isPending}
        error={
          jobQuery.error instanceof ApiError
            ? jobQuery.error
            : jobQuery.isError
              ? ({
                  code: "network_error",
                  message: "The selected job could not be reached.",
                } satisfies InvestigationDrawerError)
              : null
        }
        returnFocusRef={jobTriggerRef}
        onRetry={() => void jobQuery.refetch()}
        onClose={closeInvestigation}
      />
    </section>
  );
}
