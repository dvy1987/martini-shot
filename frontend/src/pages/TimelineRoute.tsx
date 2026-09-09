import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, Pencil } from "lucide-react";

import { ApiError } from "@/api/client";
import { createProject, getJob, getProject, getWorklist, listDeliberations, listProjects, patchWorklist, renameProject, retryWorklist } from "@/api/endpoints";
import EmptyState from "@/components/EmptyState";
import FinishBar from "@/components/FinishBar";
import InvestigationDrawer, {
  type InvestigationDrawerError,
} from "@/components/InvestigationDrawer";
import ProgressRail from "@/components/ProgressRail";
import TimelineBoard from "@/components/TimelineBoard";
import WorklistPanel from "@/components/WorklistPanel";
import { STATUS_BOARD_ORDER, STATUS_META } from "@/lib/status";
import { toggleStatus } from "@/lib/lens";
import { deriveJourney } from "@/lib/journey";
import { isNotFound } from "@/lib/errors";
import { clipName } from "@/lib/clipDisplay";
import { jobsForProject } from "@/lib/timeline";
import type { Job, JobStatus } from "@/types/api";

const EMPTY_JOBS: Job[] = [];

function phaseName(phase: string): string {
  const labels: Record<string, string> = {
    prepare: "Ready to start",
    uploading: "Upload",
    uploaded: "Upload complete",
    watching: "Ingest",
    mixing: "Fix audio",
    repairing: "Pickups",
    consulting: "Reviewing clips",
    planning: "Plan work",
    executing: "Execute",
    delivering: "Delivery",
    complete: "Complete",
    attention: "Action needed",
  };
  return labels[phase] ?? phase.replaceAll("_", " ");
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
  const [naming, setNaming] = useState<null | "create" | "rename">(null);
  const [draftName, setDraftName] = useState("");
  const jobTriggerRef = useRef<HTMLElement | null>(null);
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const createShow = useMutation({
    mutationFn: (title: string) => createProject(title),
    onSuccess: async (project) => {
      setNaming(null);
      setDraftName("");
      await projectsQuery.refetch();
      onSelectedProjectIdChange(project.project_id);
    },
  });
  const projectQuery = useQuery({
    queryKey: ["project", selectedProjectId],
    queryFn: () => getProject(selectedProjectId ?? ""),
    enabled: selectedProjectId !== null,
  });
  const renameShow = useMutation({
    mutationFn: (title: string) => renameProject(selectedProjectId ?? "", title),
    onSuccess: async () => {
      setNaming(null);
      setDraftName("");
      await projectsQuery.refetch();
      await projectQuery.refetch();
    },
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
  const worklistQuery = useQuery({
    queryKey: ["worklist", selectedProjectId],
    queryFn: async () => {
      try {
        return await getWorklist(selectedProjectId ?? "");
      } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
      }
    },
    enabled: selectedProjectId !== null,
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
  // needs_human counts as stalled too: a human may have already fixed
  // whatever raised it out of band, and retry lets that fix carry the
  // rest of the run forward instead of leaving the step stuck forever.
  const stalledItems = (worklistQuery.data?.items ?? []).filter((item) =>
    ["failed", "paused", "needs_human"].includes(item.status),
  );
  // Deliberately NOT gated on turnoverActive: retry only re-dispatches
  // items that are failed/paused/needs_human, never one already
  // queued/leased/running, so it is safe even while an unrelated step in
  // the same worklist is still moving. Only refuse before the work plan
  // exists yet (matches the backend's 409 guard).
  const worklistPlanNotBuiltYet =
    worklistStatus === "inspecting" || worklistStatus === "waiting_for_ingest";
  const canRetryStalled =
    selectedProjectId !== null && stalledItems.length > 0 && !worklistPlanNotBuiltYet;

  function retryStalledSteps() {
    if (!selectedProjectId) return;
    setWorklistMutationError(null);
    void retryWorklist(selectedProjectId)
      .then(() => {
        void worklistQuery.refetch();
        void projectQuery.refetch();
      })
      .catch(() => {
        setWorklistMutationError(
          "The stalled steps could not be restarted. Check the connection and try again.",
        );
      });
  }

  function beginCreate() {
    setNaming("create");
    setDraftName("");
  }

  function beginRename() {
    const currentTitle =
      projectQuery.data?.title ??
      projectsQuery.data?.find((project) => project.project_id === selectedProjectId)?.title ??
      "";
    setNaming("rename");
    setDraftName(currentTitle);
  }

  function submitDraftName() {
    const cleaned = draftName.trim();
    if (!cleaned) return;
    if (naming === "create") createShow.mutate(cleaned);
    if (naming === "rename" && selectedProjectId) renameShow.mutate(cleaned);
  }

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
    setProgressDetailOpen(false);
  }, [selectedProjectId]);

  useEffect(() => {
    onInvestigationOpenChange?.(inspectedJobId !== null);
  }, [inspectedJobId, onInvestigationOpenChange]);

  useEffect(() => {
    if (!lensOpen) setStatusFilter(new Set());
  }, [lensOpen]);

  const jobs = jobsForProject(projectQuery.data?.jobs ?? EMPTY_JOBS, selectedProjectId);
  const journey = deriveJourney(jobs, worklistQuery.data ?? null);
  // The evidence surfaces remain available immediately when real activity exists;
  // the guided brief and live plan above them still own the first reading order.
  const [expertOpen, setExpertOpen] = useState(true);
  const [progressDetailOpen, setProgressDetailOpen] = useState(false);

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
          {naming === "create" ? (
            <form
              className="mx-auto flex max-w-md flex-wrap items-end justify-center gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                submitDraftName();
              }}
            >
              <label className="grid flex-1 gap-1 text-left font-mono text-xs uppercase tracking-wider text-ink-muted">
                New project name
                <input
                  value={draftName}
                  onChange={(event) => setDraftName(event.target.value)}
                  autoFocus
                  maxLength={80}
                  className="w-full rounded-sm border border-line bg-surface-2 px-3 py-2 font-sans text-sm normal-case tracking-normal text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                />
              </label>
              <button
                type="submit"
                disabled={!draftName.trim() || createShow.isPending}
                className="rounded-sm border border-tungsten bg-tungsten px-4 py-2 font-mono text-xs uppercase tracking-wider text-bg transition-opacity ease-chrome hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                {createShow.isPending ? "Opening project…" : "Create project"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setNaming(null);
                  setDraftName("");
                }}
                className="rounded-sm border border-line bg-transparent px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
            </form>
          ) : (
            <button
              type="button"
              disabled={createShow.isPending}
              onClick={beginCreate}
              className="rounded-sm border border-tungsten bg-tungsten px-4 py-2 font-mono text-xs uppercase tracking-wider text-bg transition-opacity ease-chrome hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              Start a new project
            </button>
          )}
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
            Wrap it up
          </p>
          {naming === "rename" ? (
            <form
              className="mt-1 flex flex-wrap items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                submitDraftName();
              }}
            >
              <h1 id="timeline-heading" className="sr-only">
                Rename project
              </h1>
              <label className="grid gap-1 font-mono text-xs uppercase tracking-wider text-ink-muted">
                Project name
                <input
                  value={draftName}
                  onChange={(event) => setDraftName(event.target.value)}
                  autoFocus
                  maxLength={80}
                  className="min-w-48 rounded-sm border border-line bg-surface-2 px-3 py-2 font-sans text-sm normal-case tracking-normal text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                />
              </label>
              <button
                type="submit"
                disabled={!draftName.trim() || renameShow.isPending}
                className="rounded-sm border border-tungsten bg-tungsten px-3 py-2 font-mono text-xs uppercase tracking-wider text-bg disabled:opacity-50"
              >
                {renameShow.isPending ? "Saving…" : "Save name"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setNaming(null);
                  setDraftName("");
                }}
                className="rounded-sm border border-line bg-transparent px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
            </form>
          ) : (
            <div className="mt-1 flex items-center gap-2">
              <h1 id="timeline-heading" className="text-2xl text-ink">
                {projectQuery.data?.title ?? selectedProject?.title ?? "Loading project"}
              </h1>
              <button
                type="button"
                aria-label="Rename project"
                disabled={!selectedProjectId || renameShow.isPending}
                onClick={beginRename}
                className="rounded-sm p-1 text-ink-muted transition-colors ease-chrome hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                <Pencil className="size-3.5" strokeWidth={1.5} aria-hidden />
              </button>
            </div>
          )}
          {renameShow.isError ? (
            <p className="mt-2 max-w-md text-sm text-danger">The project could not be renamed.</p>
          ) : null}
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
          {naming === "create" ? (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                submitDraftName();
              }}
            >
              <label className="grid gap-1 font-mono text-xs uppercase tracking-wider text-ink-muted">
                New project name
                <input
                  value={draftName}
                  onChange={(event) => setDraftName(event.target.value)}
                  autoFocus
                  maxLength={80}
                  className="min-w-48 rounded-sm border border-line bg-surface-2 px-3 py-2 font-sans text-sm normal-case tracking-normal text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                />
              </label>
              <button
                type="submit"
                disabled={!draftName.trim() || createShow.isPending}
                className="rounded-sm border border-tungsten bg-tungsten px-3 py-2 font-mono text-xs uppercase tracking-wider text-bg disabled:opacity-50"
              >
                {createShow.isPending ? "Opening…" : "Create project"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setNaming(null);
                  setDraftName("");
                }}
                className="rounded-sm border border-line bg-transparent px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
            </form>
          ) : (
            <button
              type="button"
              disabled={createShow.isPending}
              onClick={beginCreate}
              className="rounded-sm border border-line bg-transparent px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink-muted transition-colors ease-chrome hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              New project
            </button>
          )}
          {createShow.isError ? (
            <p className="max-w-48 text-sm text-danger">A new project could not be opened.</p>
          ) : null}
        </div>
      </div>

      {selectedProjectId ? (
        <FinishBar
          key={selectedProjectId}
          projectId={selectedProjectId}
          existingJobs={jobs.filter((job) => job.station === "ingest")}
          onFinished={() => {
            void projectQuery.refetch();
            void worklistQuery.refetch();
          }}
          compact={Boolean(worklistQuery.data)}
          active={turnoverActive}
        />
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
              {canRetryStalled ? (
                <button
                  type="button"
                  onClick={retryStalledSteps}
                  className="mt-3 rounded-sm border border-tungsten bg-tungsten px-4 py-2 font-mono text-xs uppercase tracking-wider text-bg transition-opacity ease-chrome hover:opacity-90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                >
                  Retry
                </button>
              ) : null}
            </div>
          </div>
          <ProgressRail
            phase={journey.phase}
            jobs={jobs}
            worklist={worklistQuery.data ?? null}
          />
          {worklistQuery.data ? (
            <div className="mt-3">
              <button
                type="button"
                aria-expanded={progressDetailOpen}
                aria-controls="progress-detail"
                aria-label="More detail about this run"
                onClick={() => setProgressDetailOpen((open) => !open)}
                className="mx-auto flex h-8 w-8 items-center justify-center rounded-sm text-ink-muted transition-colors ease-chrome hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                <ChevronDown
                  aria-hidden
                  className={`size-4 transition-transform duration-200 ${progressDetailOpen ? "rotate-180" : ""}`}
                />
              </button>
              {progressDetailOpen ? (
                <div id="progress-detail" className="mt-3">
                  <WorklistPanel
                    worklist={worklistQuery.data}
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
                </div>
              ) : null}
            </div>
          ) : null}
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
          body="No work has started for this project yet. Upload clips and call wrap to see activity here."
        />
      ) : null}

      {projectQuery.isSuccess && jobs.length > 0 ? (
        <TimelineBoard
          projectId={selectedProjectId}
          jobs={jobs}
          selectedJobId={selectedJobId}
          onSelectJob={handleJobSelection}
          lensOpen={lensOpen}
          statusFilter={statusFilter}
          onToggleStatus={(status) => setStatusFilter((current) => toggleStatus(current, status))}
          worklist={worklistQuery.data ?? null}
          showJobsBoard={expertOpen}
        />
      ) : null}

      {selectedProjectId ? (
        <section className="mb-6 mt-6 border border-line bg-surface-1 px-5 py-4" aria-labelledby="changes-pointer-heading">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-agent">Studio</p>
          <h2 id="changes-pointer-heading" className="mt-1 text-lg text-ink">
            Add fine-grained edits to the Final cut
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-ink-muted">
            Ask for a longer take, a picture fix, lighting, coverage, or a camera move. New versions stay attached
            to the shot. Script updates are there too.
          </p>
          <a
            href="/changes"
            className="mt-3 inline-block font-mono text-[10px] uppercase tracking-wider text-tungsten underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Open Studio
          </a>
        </section>
      ) : null}

      {selectedProjectId && worklistQuery.data ? (
        <section className="mb-6 border border-line bg-surface-1 px-5 py-4" aria-labelledby="suggestions-pointer-heading">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-agent">Suggestions</p>
          <h2 id="suggestions-pointer-heading" className="mt-1 text-lg text-ink">
            Leftover station suggestions live on their own tab
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-ink-muted">
            After ingest, mix, and pickups, specialist stations look at the updated clips and send suggestions.
            Open Suggestions to watch that list fill in, then see the ranked plan and the budget cutoff.
          </p>
          <a
            href="/suggestions"
            className="mt-3 inline-block font-mono text-[10px] uppercase tracking-wider text-tungsten underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Open Suggestions
          </a>
        </section>
      ) : null}

      {selectedJobId ? (
        <p className="mt-3 font-mono text-xs text-ink-muted">
          Selected file{" "}
          <span className="text-ink">
            {clipName(jobs.find((job) => job.job_id === selectedJobId) ?? { job_id: selectedJobId, input_refs: [] })}
          </span>
        </p>
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
