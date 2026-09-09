import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";

import { ApiError, mediaUrl } from "@/api/client";
import { acceptWorklistItem, getJobClip, retryWorklistItem } from "@/api/endpoints";
import { AgentNotesModal } from "@/components/AgentNotesModal";
import ClipReviewModal from "@/components/ClipReviewModal";
import ClipThumb from "@/components/ClipThumb";
import { readAgentNotes, type AgentNotes } from "@/lib/agentNotes";
import { clipName, groupBoardLanes, withWatchNotes, type BoardRow } from "@/lib/clipDisplay";
import {
  applyFinalCutPick,
  downloadFinalCutBlobs,
  finalCutAction,
  finalCutPlaylist,
  finalCutSlots,
  groupBoardByClip,
  originKey,
  type FinalCutPick,
} from "@/lib/finalCut";
import { cost } from "@/lib/formatters";
import { filterJobsByStatus } from "@/lib/lens";
import { staggerChild, staggerParent } from "@/lib/motion";
import { canAcceptRow, canRetryRow } from "@/lib/stalledRow";
import { STATUS_BOARD_ORDER, statusMetaOrUnknown } from "@/lib/status";
import { stationName } from "@/lib/stations";
import { jobsForProject } from "@/lib/timeline";
import type { Job, JobClip, JobStatus, Worklist } from "@/types/api";

interface TimelineBoardProps {
  jobs: readonly Job[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string, trigger: HTMLElement) => void;
  lensOpen?: boolean;
  statusFilter?: ReadonlySet<JobStatus>;
  onToggleStatus?: (status: JobStatus) => void;
  projectId?: string | null;
  worklist?: Worklist | null;
  showJobsBoard?: boolean;
}

const COLLAPSED_JOB_LIMIT = 8;

function storageKey(projectId: string): string {
  return `pc-final-cut:${projectId}`;
}

function loadOverrides(projectId: string | null): Record<string, FinalCutPick> {
  if (!projectId || typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(storageKey(projectId));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, FinalCutPick>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveOverrides(projectId: string | null, overrides: Record<string, FinalCutPick>): void {
  if (!projectId || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey(projectId), JSON.stringify(overrides));
}

function stationLabel(station: string): string {
  return stationName(station);
}

function TimelineTable({
  jobs,
  selectedJobId,
  onSelectJob,
  onOpenClip,
  onOpenNotes,
  slots,
  onAddToFinalCut,
  worklist,
  projectId,
}: TimelineBoardProps & {
  onOpenClip: (clip: JobClip) => void;
  onOpenNotes: (title: string, notes: AgentNotes) => void;
  slots: ReturnType<typeof finalCutSlots>;
  onAddToFinalCut: (row: BoardRow) => void;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  async function handleRetry(job: Job) {
    if (!projectId) return;
    setRowError(null);
    setPending(`retry:${job.job_id}`);
    try {
      await retryWorklistItem(projectId, job.job_id);
    } catch {
      setRowError("This step could not be retried. Check the connection and try again.");
    } finally {
      setPending(null);
    }
  }

  async function handleAccept(job: Job) {
    if (!projectId) return;
    setRowError(null);
    setPending(`accept:${job.job_id}`);
    try {
      await acceptWorklistItem(projectId, job.job_id);
    } catch {
      setRowError("This step could not be accepted. Check the connection and try again.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="overflow-x-auto rounded-md border border-line bg-surface-1">
      <table aria-label="Season timeline jobs" className="w-full min-w-max border-collapse text-left">
        <thead className="bg-surface-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
          <tr>
            <th className="border-b border-line px-4 py-2 font-normal">Stage</th>
            <th className="border-b border-line px-4 py-2 font-normal">Clip</th>
            <th className="border-b border-line px-4 py-2 font-normal">Before</th>
            <th className="border-b border-line px-4 py-2 font-normal">After</th>
            <th className="border-b border-line px-4 py-2 font-normal">Final cut</th>
            <th className="border-b border-line px-4 py-2 font-normal">What changed</th>
            <th className="border-b border-line px-4 py-2 font-normal">Status</th>
            <th className="border-b border-line px-4 py-2 font-normal">Attempt</th>
            <th className="border-b border-line px-4 py-2 font-normal">Cost</th>
            <th className="border-b border-line px-4 py-2 font-normal">Action</th>
          </tr>
        </thead>
        <tbody>
          {groupBoardByClip(jobs, worklist).map((group) => (
            <Fragment key={group.origin}>
              <tr>
                <th
                  colSpan={10}
                  scope="colgroup"
                  className="border-b border-line bg-surface-2 px-4 py-2 text-left font-mono text-xs uppercase tracking-wider text-ink"
                >
                  {group.label}
                </th>
              </tr>
              {group.rows.map((row) => {
              const { job } = row;
              const meta = statusMetaOrUnknown(row.displayStatus);
              const selected = selectedJobId === job.job_id;
              const name = group.label;
              const stage = stationLabel(row.displayStation);
              const notes = readAgentNotes(job, row.displayStation);
              const origin = originKey(job, jobs, worklist);
              const action = finalCutAction(
                row,
                slots.find((slot) => slot.origin === origin)?.pick ?? null,
              );
              return (
                <tr
                  key={row.id}
                  data-clip={name}
                  data-stage={row.displayStation}
                  className={selected ? "bg-surface-2" : "bg-surface-1"}
                >
                  <td className="border-b border-line px-4 py-2">
                    <p className="font-mono text-xs uppercase tracking-wider text-ink">{stage}</p>
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    <button
                      type="button"
                      aria-label={`Select ${name} (${stage})`}
                      aria-pressed={selected}
                      onClick={(event) => onSelectJob(job.job_id, event.currentTarget)}
                      className="text-sm text-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                    >
                      {name}
                    </button>
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    <ClipCell
                      row={row}
                      side="before"
                      name={name}
                      jobs={jobs}
                      onOpen={onOpenClip}
                    />
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    <ClipCell
                      row={row}
                      side="after"
                      name={name}
                      jobs={jobs}
                      onOpen={onOpenClip}
                    />
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    {action === "Final Cut" ? (
                      <span className="font-mono text-xs uppercase tracking-wider text-ink">
                        Final Cut
                      </span>
                    ) : action === "Add to final cut" ? (
                      <button
                        type="button"
                        onClick={() => onAddToFinalCut(row)}
                        className="text-sm text-tungsten underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                      >
                        Add to final cut
                      </button>
                    ) : (
                      <span className="text-xs text-ink-muted">—</span>
                    )}
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    <p className="text-sm text-ink">{notes.changed}</p>
                    <button
                      type="button"
                      aria-label={`Agent notes for ${name} (${stage})`}
                      onClick={() => onOpenNotes(`${name} · ${stage}`, notes)}
                      className="mt-1 text-sm text-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                    >
                      Agent Notes
                    </button>
                  </td>
                  <td className={`border-b border-line px-4 py-2 font-mono text-xs ${meta.textClass}`}>
                    <span aria-hidden className="mr-2">{meta.glyph}</span>
                    {meta.term}
                  </td>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink-muted">
                    {job.attempts}
                  </td>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink-muted">
                    {job.cost_micros !== undefined ? cost(job.cost_micros) : "—"}
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    {canRetryRow(job, worklist) || canAcceptRow(job, worklist) ? (
                      <div className="flex flex-wrap items-center gap-3">
                        {canRetryRow(job, worklist) ? (
                          <button
                            type="button"
                            aria-label={`Retry ${name} (${stage})`}
                            disabled={pending === `retry:${job.job_id}`}
                            onClick={() => void handleRetry(job)}
                            className="text-sm text-tungsten underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Retry
                          </button>
                        ) : null}
                        {canAcceptRow(job, worklist) ? (
                          <button
                            type="button"
                            aria-label={`Accept ${name} (${stage})`}
                            disabled={pending === `accept:${job.job_id}`}
                            onClick={() => void handleAccept(job)}
                            className="text-sm text-tungsten underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Accept
                          </button>
                        ) : null}
                      </div>
                    ) : (
                      <span className="text-xs text-ink-muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
            </Fragment>
          ))}
        </tbody>
      </table>
      {rowError ? (
        <p className="border-t border-line px-4 py-2 text-sm text-danger">{rowError}</p>
      ) : null}
    </div>
  );
}

function ClipCell({
  row,
  side,
  name,
  jobs,
  onOpen,
}: {
  row: BoardRow;
  side: "before" | "after";
  name: string;
  jobs: readonly Job[];
  onOpen: (clip: JobClip) => void;
}) {
  const open = (clip: JobClip) => {
    onOpen(
      row.displayStation === "upload" ? clip : withWatchNotes(clip, row.job, jobs),
    );
  };
  if (side === "before") {
    if (row.before === "none") {
      return (
        <span aria-label="No clip before this step" className="text-xs text-ink-muted">
          —
        </span>
      );
    }
    return <ClipThumb jobId={row.job.job_id} side="before" label={name} onOpen={open} />;
  }
  if (row.after === "clip") {
    return (
      <ClipThumb
        jobId={row.job.job_id}
        side={row.afterSide}
        reviewSide="after"
        label={`${name} after`}
        onOpen={open}
      />
    );
  }
  return (
    <span className="text-xs text-ink-muted">
      {row.after === "pending" ? "Still working" : "No change"}
    </span>
  );
}

function FinalCutStrip({
  slots,
  onOpenClip,
}: {
  slots: ReturnType<typeof finalCutSlots>;
  onOpenClip: (clip: JobClip) => void;
}) {
  const playlist = finalCutPlaylist(slots);
  const [phase, setPhase] = useState<"idle" | "downloading" | "playing" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [objectUrls, setObjectUrls] = useState<string[]>([]);
  const [index, setIndex] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    return () => {
      for (const url of objectUrls) URL.revokeObjectURL(url);
    };
  }, [objectUrls]);

  useEffect(() => {
    if (phase !== "playing") return;
    void videoRef.current?.play();
  }, [phase, index]);

  async function handlePlay() {
    if (playlist.length === 0 || phase === "downloading") return;
    for (const url of objectUrls) URL.revokeObjectURL(url);
    setObjectUrls([]);
    setPhase("downloading");
    setError(null);
    try {
      const urls = await downloadFinalCutBlobs(playlist, {
        getClip: async (jobId, side) => {
          try {
            return await getJobClip(jobId, side);
          } catch (err) {
            if (err instanceof ApiError && err.status === 502) {
              return {
                job_id: jobId,
                side,
                clip_name: "",
                url: `/api/v1/jobs/${encodeURIComponent(jobId)}/clip/${side}/media`,
                expires_in_minutes: 60,
                metadata: {},
              };
            }
            throw err;
          }
        },
        fetchBlob: async (url) => {
          const response = await fetch(mediaUrl(url));
          if (!response.ok) {
            throw new Error("The clip could not be downloaded.");
          }
          return response.blob();
        },
        toObjectUrl: (blob) => URL.createObjectURL(blob),
      });
      setObjectUrls(urls);
      setIndex(0);
      setPhase("playing");
    } catch {
      setPhase("error");
      setError("The final cut could not be downloaded.");
    }
  }

  function handleEnded() {
    if (index + 1 >= objectUrls.length) {
      setPhase("idle");
      setIndex(0);
      return;
    }
    setIndex(index + 1);
  }

  // Play only needs a playlist, not a fully stopped run: it plays whatever
  // has actually passed right now, same as the slots themselves. Waiting
  // for orchestratorHasStopped() here would reintroduce the exact bug the
  // slots just got fixed for — the aggregate worklist status can say
  // "running" indefinitely because of one unrelated stuck item, even
  // while every clip already has a perfectly playable After.
  const canPlay = playlist.length > 0;
  const playLabel = phase === "downloading" ? "Downloading" : phase === "playing" ? "Playing" : "Play";

  return (
    <section
      aria-label="Final cut"
      className="mt-4 rounded-md border border-line bg-surface-1 px-4 py-3"
    >
      <header className="mb-3">
        <h3 className="font-mono text-xs uppercase tracking-widest text-ink">Final cut</h3>
        <p className="mt-1 text-sm text-ink-muted">
          The last successful After of each original clip so far, in upload order. Updates live
          as steps finish, fail, or stall. Add a different After from the table to swap it.
        </p>
      </header>
      {slots.length === 0 ? (
        <p className="font-mono text-xs uppercase tracking-wider text-ink-muted">
          No original clips yet.
        </p>
      ) : (
        <div className="flex items-center gap-3">
          <ol className="flex min-w-0 flex-1 gap-3 overflow-x-auto">
            {slots.map((slot, slotIndex) => (
              <li key={slot.origin} className="min-w-28">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                  Clip {slotIndex + 1}
                </p>
                {slot.pick ? (
                  <ClipThumb
                    jobId={slot.pick.jobId}
                    side={slot.pick.side}
                    label={slot.name}
                    reviewSide="after"
                    onOpen={onOpenClip}
                  />
                ) : (
                  <p className="text-xs text-ink-muted">No After yet</p>
                )}
              </li>
            ))}
          </ol>
          <button
            type="button"
            disabled={!canPlay || phase === "downloading"}
            onClick={() => void handlePlay()}
            className="shrink-0 rounded-sm border border-tungsten bg-tungsten px-3 py-2 font-mono text-xs uppercase tracking-wider text-bg transition-colors ease-chrome hover:border-ink hover:bg-ink disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            {playLabel}
          </button>
        </div>
      )}
      {error ? <p className="mt-3 border-l-2 border-danger pl-3 text-sm text-danger">{error}</p> : null}
      {phase === "playing" && objectUrls[index] ? (
        <video
          ref={videoRef}
          key={objectUrls[index]}
          role="video"
          aria-label="Final cut playback"
          src={objectUrls[index]}
          controls
          autoPlay
          className="mt-3 w-full max-w-3xl rounded-sm border border-line bg-surface-2"
          onEnded={handleEnded}
        />
      ) : null}
    </section>
  );
}

export default function TimelineBoard({
  jobs,
  selectedJobId,
  onSelectJob,
  lensOpen = false,
  statusFilter,
  onToggleStatus,
  projectId = null,
  worklist = null,
  showJobsBoard = true,
}: TimelineBoardProps) {
  const projectJobs = useMemo(
    () => (projectId ? jobsForProject(jobs, projectId) : [...jobs]),
    [jobs, projectId],
  );
  const visibleJobs = statusFilter ? filterJobsByStatus(projectJobs, statusFilter) : [...projectJobs];
  const lanes = groupBoardLanes(visibleJobs);
  const [view, setView] = useState<"timeline" | "table">("timeline");
  const [expandedStations, setExpandedStations] = useState<Set<string>>(() => new Set());
  const [reviewClip, setReviewClip] = useState<JobClip | null>(null);
  const [agentNotes, setAgentNotes] = useState<{ title: string; notes: AgentNotes } | null>(null);
  const [overrides, setOverrides] = useState<Record<string, FinalCutPick>>(() =>
    loadOverrides(projectId ?? null),
  );
  const slots = useMemo(
    () => finalCutSlots(projectJobs, overrides, worklist),
    [projectJobs, overrides, worklist],
  );
  useEffect(() => {
    setOverrides(loadOverrides(projectId ?? null));
  }, [projectId]);

  useEffect(() => {
    if (lensOpen) {
      setExpandedStations(new Set(groupBoardLanes(projectJobs).map((lane) => lane.station)));
      return;
    }
    setExpandedStations(new Set());
  }, [lensOpen, projectJobs]);

  function toggleStation(station: string) {
    setExpandedStations((current) => {
      const next = new Set(current);
      if (next.has(station)) next.delete(station);
      else next.add(station);
      return next;
    });
  }

  function handleAddToFinalCut(row: BoardRow) {
    const origin = originKey(row.job, projectJobs, worklist);
    if (!origin || row.after !== "clip") return;
    setOverrides((current) => {
      const next = applyFinalCutPick(current, origin, {
        jobId: row.job.job_id,
        side: row.afterSide,
      });
      saveOverrides(projectId ?? null, next);
      return next;
    });
  }

  return (
    <div>
      {showJobsBoard ? (
        <>
      <div
        role="group"
        aria-label="Timeline display"
        className="mb-3 flex justify-end gap-1"
      >
        <button
          type="button"
          aria-pressed={view === "timeline"}
          onClick={() => setView("timeline")}
          className={`rounded-sm border px-3 py-1.5 font-mono text-xs uppercase tracking-wider transition-colors ease-chrome focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten ${
            view === "timeline"
              ? "border-tungsten bg-surface-2 text-ink"
              : "border-line bg-surface-1 text-ink-muted hover:border-ink-muted"
          }`}
        >
          Timeline view
        </button>
        <button
          type="button"
          aria-pressed={view === "table"}
          onClick={() => setView("table")}
          className={`rounded-sm border px-3 py-1.5 font-mono text-xs uppercase tracking-wider transition-colors ease-chrome focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten ${
            view === "table"
              ? "border-tungsten bg-surface-2 text-ink"
              : "border-line bg-surface-1 text-ink-muted hover:border-ink-muted"
          }`}
        >
          Table view
        </button>
      </div>

      {lensOpen && onToggleStatus ? (
        <fieldset className="mb-3 rounded-md border border-line bg-surface-1 px-4 py-3">
          <legend className="font-mono text-xs uppercase tracking-widest text-ink-muted">
            Lens filters
          </legend>
          <div role="group" aria-label="Filter jobs by status" className="mt-2 flex flex-wrap gap-1">
            {STATUS_BOARD_ORDER.map((status) => {
              const meta = statusMetaOrUnknown(status);
              const pressed = Boolean(statusFilter?.has(status));
              return (
                <button
                  key={status}
                  type="button"
                  aria-pressed={pressed}
                  onClick={() => onToggleStatus(status)}
                  className={`rounded-sm border px-3 py-1.5 font-mono text-xs uppercase tracking-wider transition-colors ease-chrome focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten ${
                    pressed
                      ? "border-tungsten bg-surface-2 text-ink"
                      : "border-line bg-surface-1 text-ink-muted hover:border-ink-muted"
                  }`}
                >
                  <span aria-hidden className="mr-2">
                    {meta.glyph}
                  </span>
                  {meta.term}
                </button>
              );
            })}
          </div>
        </fieldset>
      ) : null}

      {projectJobs.length > 0 && visibleJobs.length === 0 ? (
        <p className="mb-3 font-mono text-xs uppercase tracking-widest text-ink-muted">
          No observed jobs match the Lens filter.
        </p>
      ) : null}

      {view === "table" ? (
        <TimelineTable
          jobs={visibleJobs}
          selectedJobId={selectedJobId}
          onSelectJob={onSelectJob}
          onOpenClip={setReviewClip}
          onOpenNotes={(title, notes) => setAgentNotes({ title, notes })}
          slots={slots}
          onAddToFinalCut={handleAddToFinalCut}
          worklist={worklist}
          projectId={projectId}
        />
      ) : (
        <motion.div
          variants={staggerParent}
          initial="hidden"
          animate="visible"
          className="overflow-x-auto rounded-md border border-line bg-surface-1"
        >
          <div className="min-w-max">
            <div className="grid grid-cols-[14rem_1fr] border-b border-line bg-surface-2 px-4 py-2">
              <span className="font-mono text-xs uppercase tracking-widest text-ink-muted">
                Stage
              </span>
              <span className="font-mono text-xs uppercase tracking-widest text-ink-muted">
                Season activity
              </span>
            </div>

            {lanes.map((lane) => {
              const expanded = expandedStations.has(lane.station);
              const hiddenCount = Math.max(0, lane.rows.length - COLLAPSED_JOB_LIMIT);
              const visibleRows = expanded ? lane.rows : lane.rows.slice(0, COLLAPSED_JOB_LIMIT);

              return (
                <motion.section
                  key={lane.station}
                  variants={staggerChild}
                  aria-label={`${stationLabel(lane.station)} station`}
                  className="grid grid-cols-[14rem_1fr] border-b border-line px-4 py-2 last:border-b-0"
                >
                  <div className="pr-4">
                    <h2 className="font-mono text-xs uppercase tracking-wider text-ink">
                      {stationLabel(lane.station)}
                    </h2>
                  </div>

                  <div className="grid auto-cols-fr grid-flow-col gap-2">
                    {visibleRows.map((row) => {
                      const { job } = row;
                      const meta = statusMetaOrUnknown(row.displayStatus);
                      const selected = selectedJobId === job.job_id;
                      const name = clipName(job);
                      const stage = stationLabel(row.displayStation);

                      return (
                        <button
                          key={row.id}
                          type="button"
                          aria-label={`${meta.term}: ${name} · ${stage}`}
                          aria-pressed={selected}
                          title={`${meta.term}: ${name} · ${stage}`}
                          onClick={(event) => onSelectJob(job.job_id, event.currentTarget)}
                          className={[
                            "group min-w-36 rounded-md border bg-surface-2 px-3 py-2 text-left",
                            "cursor-pointer transition-[border-color,background-color,transform] ease-chrome hover:border-ink-muted hover:-translate-y-px active:translate-y-0 active:bg-surface-1",
                            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten",
                            selected ? "border-tungsten ring-1 ring-tungsten" : "border-line",
                            job.cost_micros !== undefined ? "border-r-2 border-r-tungsten" : "",
                          ].join(" ")}
                        >
                          <span className={`block font-mono text-xs ${meta.textClass}`}>
                            <span aria-hidden className="mr-2">{meta.glyph}</span>
                            {meta.term}
                          </span>
                          <span className="mt-1 block truncate text-sm text-ink">
                            {name}
                          </span>
                          <span className="mt-1 flex justify-between gap-3 font-mono text-xs text-ink-muted">
                            <span>TRY {job.attempts}</span>
                            {job.cost_micros !== undefined ? <span>{cost(job.cost_micros)}</span> : null}
                          </span>
                        </button>
                      );
                    })}

                    {hiddenCount > 0 ? (
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-label={
                          expanded
                            ? `Collapse ${stationLabel(lane.station)} lane`
                            : `Show ${hiddenCount} more ${hiddenCount === 1 ? "job" : "jobs"} in ${stationLabel(lane.station)}`
                        }
                        onClick={() => toggleStation(lane.station)}
                        className="flex min-w-16 items-center justify-center rounded-md border border-line bg-surface-2 px-3 font-mono text-xs text-ink-muted transition-colors ease-chrome hover:border-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                      >
                        {expanded ? "Collapse" : `+${hiddenCount}`}
                      </button>
                    ) : null}
                  </div>
                </motion.section>
              );
            })}
          </div>
        </motion.div>
      )}
        </>
      ) : null}

      <FinalCutStrip slots={slots} onOpenClip={setReviewClip} />

      {reviewClip ? <ClipReviewModal clip={reviewClip} onClose={() => setReviewClip(null)} /> : null}
      {agentNotes ? (
        <AgentNotesModal
          title={agentNotes.title}
          notes={agentNotes.notes}
          onClose={() => setAgentNotes(null)}
        />
      ) : null}
    </div>
  );
}