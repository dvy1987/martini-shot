import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { createProject, getJob, getProject, getWorklist, listDeliberations, listProjectShots, listProjects, patchWorklist } from "@/api/endpoints";
import AlternatesLane from "@/components/AlternatesLane";
import EmptyState from "@/components/EmptyState";
import FinishBar from "@/components/FinishBar";
import InvestigationDrawer, {
  type InvestigationDrawerError,
} from "@/components/InvestigationDrawer";
import RevisionRoom from "@/components/RevisionRoom";
import TimelineBoard from "@/components/TimelineBoard";
import WorklistPanel from "@/components/WorklistPanel";
import { STATUS_BOARD_ORDER, STATUS_META } from "@/lib/status";
import { toggleStatus } from "@/lib/lens";
import { deriveJourney } from "@/lib/journey";
import { cost } from "@/lib/formatters";
import type { Job, JobStatus } from "@/types/api";

const EMPTY_JOBS: Job[] = [];

function stationName(station: string): string {
  const labels: Record<string, string> = {
    ingest: "File check",
    loudness: "Audio check",
    pickups: "Picture repair",
    extend: "Extend a shot",
    corrections: "Fix an image",
    relight: "Improve lighting",
    coverage: "Add coverage",
    camera_language: "Camera movement",
    dub: "Create a dubbed version",
    delivery: "Delivery check",
    spend: "Budget check",
  };
  return labels[station] ?? station.replaceAll("_", " ");
}

function phaseName(phase: string): string {
  const labels: Record<string, string> = {
    prepare: "Ready to start",
    ingesting: "Checking files",
    mixing: "Fixing audio",
    repairing: "Checking picture",
    consulting: "Reviewing clips",
    planning: "Choosing improvements",
    executing: "Running selected work",
    complete: "Complete",
    attention: "Action needed",
  };
  return labels[phase] ?? phase.replaceAll("_", " ");
}

function taskStatus(status: string): string {
  const labels: Record<string, string> = {
    waiting: "Waiting for budget",
    queued: "Queued",
    running: "Running",
    passed: "Complete",
    failed: "Failed",
    needs_human: "Needs review",
    paused: "Paused",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

interface TimelineRouteProps {
  selectedProjectId: string | null;
  onSelectedProjectIdChange: (projectId: string | null) => void;
  lensOpen?: boolean;
  pendingJobId?: string | null;
  onPendingJobConsumed?: () => void;
  onInvestigationOpenChange?: (open: boolean) => void;
}

function StatusLegend() {
  return (
    <section className="mt-8 rounded-md border border-line bg-surface-1 p-4">
      <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">
        Reading the board
      </h2>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        {STATUS_BOARD_ORDER.map((status) => {
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
  lensOpen = false,
  pendingJobId = null,
  onPendingJobConsumed,
  onInvestigationOpenChange,
}: TimelineRouteProps) {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [inspectedJobId, setInspectedJobId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<Set<JobStatus>>(() => new Set());
  const [worklistMutationError, setWorklistMutationError] = useState<string | null>(null);
  const jobTriggerRef = useRef<HTMLElement | null>(null);
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const createShow = useMutation({
    mutationFn: () => createProject(),
    onSuccess: async (project) => {
      await projectsQuery.refetch();
      onSelectedProjectIdChange(project.project_id);
    },
  });
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
  const deliberationQuery = useQuery({
    queryKey: ["deliberations", selectedProjectId, inspectedJobId],
    queryFn: () => listDeliberations(selectedProjectId ?? "", inspectedJobId ?? ""),
    enabled: inspectedJobId !== null && selectedProjectId !== null,
  });
  const shotsQuery = useQuery({
    queryKey: ["shots", selectedProjectId],
    queryFn: () => listProjectShots(selectedProjectId ?? ""),
    enabled: selectedProjectId !== null,
  });
  const worklistQuery = useQuery({
    queryKey: ["worklist", selectedProjectId],
    queryFn: () => getWorklist(selectedProjectId ?? ""),
    enabled: selectedProjectId !== null,
    retry: false,
  });
  const worklistStatus = worklistQuery.data?.status ?? "";
  const worklistHasActiveItems = Boolean(
    worklistQuery.data?.items.some((item) =>
      ["queued", "leased", "running"].includes(item.status),
    ),
  );
  const turnoverActive =
    worklistHasActiveItems ||
    worklistStatus === "running" ||
    worklistStatus === "waiting_for_ingest" ||
    worklistStatus === "inspecting";

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

  useEffect(() => {
    onInvestigationOpenChange?.(inspectedJobId !== null);
  }, [inspectedJobId, onInvestigationOpenChange]);

  useEffect(() => {
    if (!lensOpen) setStatusFilter(new Set());
  }, [lensOpen]);

  const jobs = projectQuery.data?.jobs ?? EMPTY_JOBS;
  const journey = deriveJourney(jobs, worklistQuery.data ?? null);
  // The evidence surfaces remain available immediately when real activity exists;
  // the guided brief and live plan above them still own the first reading order.
  const [expertOpen, setExpertOpen] = useState(true);

  useEffect(() => {
    if (!pendingJobId || !projectQuery.isSuccess) return;
    const match = jobs.some((job) => job.job_id === pendingJobId);
    if (match) {
      setSelectedJobId(pendingJobId);
      setInspectedJobId(pendingJobId);
    }
    onPendingJobConsumed?.();
  }, [jobs, onPendingJobConsumed, pendingJobId, projectQuery.isSuccess]);

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
          title="No projects yet"
          body="Start a new project, then drop your clips in order. You can open any existing project from the list once you have one."
        />
        <div className="mt-5 text-center">
          <button
            type="button"
            disabled={createShow.isPending}
            onClick={() => createShow.mutate()}
            className="rounded-sm border border-tungsten bg-tungsten px-4 py-2 font-mono text-xs uppercase tracking-wider text-bg transition-opacity ease-chrome hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            {createShow.isPending ? "Opening project…" : "Start a new project"}
          </button>
          {createShow.isError ? (
            <p className="mt-3 text-sm text-danger">
              A new project could not be opened. Check the connection and try again.
            </p>
          ) : null}
        </div>
        <StatusLegend />
      </section>
    );
  }

  const selectedProject = projectsQuery.data.find(
    ({ project_id }) => project_id === selectedProjectId,
  );

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
        <div className="flex flex-wrap items-end gap-3">
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
          <button
            type="button"
            disabled={createShow.isPending}
            onClick={() => createShow.mutate()}
            className="rounded-sm border border-line bg-transparent px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink-muted transition-colors ease-chrome hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            {createShow.isPending ? "Opening…" : "New project"}
          </button>
          {createShow.isError ? (
            <p className="max-w-48 text-sm text-danger">A new project could not be opened.</p>
          ) : null}
        </div>
      </div>

      {selectedProjectId ? (
        <FinishBar
          key={selectedProjectId}
          projectId={selectedProjectId}
          onFinished={() => {
            void projectQuery.refetch();
            void worklistQuery.refetch();
          }}
          compact={Boolean(worklistQuery.data)}
          active={turnoverActive}
        />
      ) : null}

      {selectedProjectId && worklistQuery.data ? (
        <section className="mb-6 border border-line bg-surface-1" aria-labelledby="plan-heading">
          <header className="border-b border-line px-5 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-agent">Plan for this run</p>
                <h2 id="plan-heading" className="mt-1 text-lg text-ink">What Martini Shot found</h2>
              </div>
              <p className="font-mono text-xs tabular-nums text-ink-muted">{cost(worklistQuery.data.spent_micros)} spent / {cost(worklistQuery.data.budget_micros)} budget</p>
            </div>
            {worklistQuery.data.rank_reason ? <p className="mt-3 max-w-3xl border-l-2 border-agent px-3 text-sm text-ink">{worklistQuery.data.rank_reason}</p> : null}
          </header>
          <div className="grid gap-0 lg:grid-cols-2">
            <div className="border-b border-line p-5 lg:border-b-0 lg:border-r">
              <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Agent reviews</h3>
              {worklistQuery.data.attendance.length === 0 ? <p className="mt-3 text-sm text-ink-muted">No agent reviews yet.</p> : <ul className="mt-3 space-y-3">{worklistQuery.data.attendance.slice(0, 5).map((row, index) => <li key={`${row.station}-${row.shot_id ?? "project"}-${index}`}><div className="flex items-baseline justify-between gap-3"><span className="font-mono text-xs uppercase text-ink">{stationName(row.station)}</span><span className="font-mono text-[10px] uppercase text-ink-muted">{taskStatus(row.status)}</span></div>{row.status !== "empty" ? <p className="mt-1 text-sm text-ink-muted">{row.summary}{row.impact !== "none" ? ` · ${row.impact} impact` : ""}</p> : null}</li>)}</ul>}
            </div>
            <div className="p-5">
              <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Selected work</h3>
              {worklistQuery.data.items.length === 0 ? <p className="mt-3 text-sm text-ink-muted">Martini Shot is still deciding what to run.</p> : <ol className="mt-3 space-y-2">{worklistQuery.data.items.slice(0, 6).map((item, index) => <li key={item.id} className="border-b border-line pb-2 last:border-0"><div className="flex gap-3"><span className="font-mono text-xs text-tungsten">{String(index + 1).padStart(2, "0")}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap justify-between gap-2"><span className="font-mono text-xs uppercase text-ink">{stationName(item.station)}</span><span className="font-mono text-[10px] uppercase text-ink-muted">{taskStatus(item.status)}</span></div>{item.summary ? <p className="mt-1 text-sm text-ink-muted">{item.summary}</p> : null}{item.blocked_by?.length ? <p className="mt-1 font-mono text-[10px] uppercase text-tungsten">Waiting for: {item.blocked_by.map((id) => stationName(id.split("::")[0])).join(", ")}</p> : null}</div></div></li>)}</ol>}
            </div>
          </div>
        </section>
      ) : null}

      {selectedProjectId ? (
        <section className="mb-6 border border-line bg-surface-1 px-5 py-4" aria-live="polite">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-agent">Current progress</p>
              <h2 className="mt-1 text-xl text-ink">{journey.label}</h2>
              <p className="mt-1 max-w-2xl text-sm text-ink-muted">{journey.detail}</p>
            </div>
            <div className="text-right font-mono text-xs text-ink-muted">
              <p className="uppercase tracking-wider">{phaseName(journey.phase)}</p>
              {journey.total > 0 ? <p className="mt-1 tabular-nums text-ink">{journey.completed} / {journey.total} complete</p> : null}
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {([
              ["ingesting", "Check files"],
              ["mixing", "Fix audio"],
              ["repairing", "Check picture"],
              ["consulting", "Review clips"],
              ["planning", "Choose work"],
              ["executing", "Run selected work"],
            ] as const).map(([phase, label]) => {
              const phaseOrder = ["ingesting", "mixing", "repairing", "consulting", "planning", "executing"];
              const currentIndex = journey.phase === "complete" ? phaseOrder.length : phaseOrder.indexOf(journey.phase);
              const phaseIndex = phaseOrder.indexOf(phase);
              const active = journey.phase === phase;
              const complete = currentIndex > phaseIndex;
              return (
              <div key={phase} className={`border-t-2 pt-2 font-mono text-[10px] uppercase tracking-wider ${active ? "border-tungsten text-ink" : complete ? "border-signal text-ink-muted" : "border-line text-ink-muted"}`}>
                {label}
              </div>
              );
            })}
          </div>
          {worklistQuery.isError ? (
            <div className="mt-4 border-l-2 border-danger pl-3 text-sm text-danger">
              The current work plan could not be loaded.
              <button type="button" onClick={() => void worklistQuery.refetch()} className="ml-2 font-mono text-[10px] uppercase underline underline-offset-4 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">Retry</button>
            </div>
          ) : null}
          {worklistMutationError ? <p className="mt-3 border-l-2 border-danger pl-3 text-sm text-danger">{worklistMutationError}</p> : null}
          <button type="button" onClick={() => setExpertOpen((open) => !open)} className="mt-4 border-b border-line pb-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">
            {expertOpen ? "Hide technical details" : "Show technical details"}
          </button>
        </section>
      ) : null}

      {projectQuery.isPending || !selectedProjectId ? <TimelineSkeleton /> : null}

      {projectQuery.isError
        ? (() => {
            const error =
              projectQuery.error instanceof ApiError
                ? projectQuery.error
                : new ApiError("network_error", "The selected project could not be reached.", 0);
            return (
              <div className="rounded-md border border-line bg-surface-1 px-6 py-10 text-center">
                <p className="text-xl text-ink">This project could not be loaded.</p>
                <p className="mt-2 text-sm text-ink-muted">{error.message}</p>
                <p className="mt-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
                  {error.code}
                </p>
                <button
                  type="button"
                  onClick={() => void projectQuery.refetch()}
                  className="mt-5 rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted active:bg-surface-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                >
                  Try again
                </button>
              </div>
            );
          })()
        : null}

      {projectQuery.isSuccess && jobs.length === 0 ? (
        <EmptyState
          glyph="▤"
          title="No activity yet"
          body="No work has started for this project yet. Upload clips and start a finishing run to see activity here."
        />
      ) : null}

      {projectQuery.isSuccess && jobs.length > 0 && expertOpen ? (
        <TimelineBoard
          jobs={jobs}
          selectedJobId={selectedJobId}
          onSelectJob={handleJobSelection}
          lensOpen={lensOpen}
          statusFilter={statusFilter}
          onToggleStatus={(status) => setStatusFilter((current) => toggleStatus(current, status))}
        />
      ) : null}

      {selectedJobId ? (
        <p className="mt-3 font-mono text-xs text-ink-muted">
          Selected file <span className="text-ink">{selectedJobId}</span>
        </p>
      ) : null}

      {projectQuery.isSuccess && selectedProjectId && expertOpen ? (
        <AlternatesLane shots={shotsQuery.data ?? []} />
      ) : null}

      {selectedProjectId && expertOpen ? <RevisionRoom projectId={selectedProjectId} /> : null}

      {selectedProjectId && expertOpen ? (
        <WorklistPanel
          worklist={worklistQuery.data ?? null}
          onReorder={(order) => {
            setWorklistMutationError(null);
            void patchWorklist(selectedProjectId, order)
              .then(() => {
                void worklistQuery.refetch();
              })
              .catch((error: unknown) => {
                setWorklistMutationError(
                  error instanceof Error ? error.message : "The work order could not be saved.",
                );
              });
          }}
        />
      ) : null}

      {lensOpen || jobs.length === 0 ? <StatusLegend /> : null}

      <InvestigationDrawer
        open={inspectedJobId !== null}
        job={jobQuery.data ?? null}
        isLoading={jobQuery.isPending}
        deliberation={deliberationQuery.data?.[0] ?? null}
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
