import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { cost } from "@/lib/formatters";
import { filterJobsByStatus } from "@/lib/lens";
import { staggerChild, staggerParent } from "@/lib/motion";
import { STATUS_BOARD_ORDER, statusMetaOrUnknown } from "@/lib/status";
import { groupJobsByStation } from "@/lib/timeline";
import type { Job, JobStatus } from "@/types/api";

interface TimelineBoardProps {
  jobs: readonly Job[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string, trigger: HTMLElement) => void;
  lensOpen?: boolean;
  statusFilter?: ReadonlySet<JobStatus>;
  onToggleStatus?: (status: JobStatus) => void;
}

const COLLAPSED_JOB_LIMIT = 8;

function stationLabel(station: string): string {
  return station.replaceAll("_", " ");
}

function TimelineTable({
  jobs,
  selectedJobId,
  onSelectJob,
}: TimelineBoardProps) {
  return (
    <div className="overflow-x-auto rounded-md border border-line bg-surface-1">
      <table aria-label="Season timeline jobs" className="w-full min-w-max border-collapse text-left">
        <thead className="bg-surface-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
          <tr>
            <th className="border-b border-line px-4 py-2 font-normal">Station</th>
            <th className="border-b border-line px-4 py-2 font-normal">Job</th>
            <th className="border-b border-line px-4 py-2 font-normal">Status</th>
            <th className="border-b border-line px-4 py-2 font-normal">Attempt</th>
            <th className="border-b border-line px-4 py-2 font-normal">Cost</th>
          </tr>
        </thead>
        <tbody>
          {groupJobsByStation(jobs).flatMap((lane) =>
            lane.jobs.map((job) => {
              const meta = statusMetaOrUnknown(job.status);
              const selected = selectedJobId === job.job_id;
              return (
                <tr key={job.job_id} className={selected ? "bg-surface-2" : "bg-surface-1"}>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink-muted">
                    {stationLabel(job.station)}
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    <button
                      type="button"
                      aria-label={`Select job ${job.job_id}`}
                      aria-pressed={selected}
                      onClick={(event) => onSelectJob(job.job_id, event.currentTarget)}
                      className="font-mono text-xs text-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                    >
                      {job.job_id}
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
                </tr>
              );
            }),
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function TimelineBoard({
  jobs,
  selectedJobId,
  onSelectJob,
  lensOpen = false,
  statusFilter,
  onToggleStatus,
}: TimelineBoardProps) {
  const visibleJobs = statusFilter ? filterJobsByStatus(jobs, statusFilter) : [...jobs];
  const lanes = groupJobsByStation(visibleJobs);
  const [view, setView] = useState<"timeline" | "table">("timeline");
  const [expandedStations, setExpandedStations] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (lensOpen) {
      setExpandedStations(new Set(groupJobsByStation(jobs).map((lane) => lane.station)));
      return;
    }
    setExpandedStations(new Set());
  }, [lensOpen, jobs]);

  function toggleStation(station: string) {
    setExpandedStations((current) => {
      const next = new Set(current);
      if (next.has(station)) next.delete(station);
      else next.add(station);
      return next;
    });
  }

  return (
    <div>
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

      {jobs.length > 0 && visibleJobs.length === 0 ? (
        <p className="mb-3 font-mono text-xs uppercase tracking-widest text-ink-muted">
          No observed jobs match the Lens filter.
        </p>
      ) : null}

      {view === "table" ? (
        <TimelineTable jobs={visibleJobs} selectedJobId={selectedJobId} onSelectJob={onSelectJob} />
      ) : (
        <motion.div
          variants={staggerParent}
          initial="hidden"
          animate="visible"
          className="overflow-x-auto rounded-md border border-line bg-surface-1"
        >
          <div className="min-w-max">
            <div className="grid grid-cols-[10rem_1fr] border-b border-line bg-surface-2 px-4 py-2">
              <span className="font-mono text-xs uppercase tracking-widest text-ink-muted">
                Station
              </span>
              <span className="font-mono text-xs uppercase tracking-widest text-ink-muted">
                Season activity
              </span>
            </div>

            {lanes.map((lane) => {
              const expanded = expandedStations.has(lane.station);
              const hiddenCount = Math.max(0, lane.jobs.length - COLLAPSED_JOB_LIMIT);
              const visibleJobs = expanded ? lane.jobs : lane.jobs.slice(0, COLLAPSED_JOB_LIMIT);

              return (
                <motion.section
                  key={lane.station}
                  variants={staggerChild}
                  aria-label={`${stationLabel(lane.station)} station`}
                  className="grid grid-cols-[10rem_1fr] border-b border-line px-4 py-2 last:border-b-0"
                >
                  <div className="flex items-center pr-4">
                    <h2 className="font-mono text-xs uppercase tracking-wider text-ink">
                      {stationLabel(lane.station)}
                    </h2>
                  </div>

                  <div className="grid auto-cols-fr grid-flow-col gap-2">
                    {visibleJobs.map((job) => {
                      const meta = statusMetaOrUnknown(job.status);
                      const selected = selectedJobId === job.job_id;

                      return (
                        <button
                          key={job.job_id}
                          type="button"
                          aria-label={`${meta.term}: ${job.job_id}`}
                          aria-pressed={selected}
                          title={`${meta.term}: ${job.job_id}`}
                          onClick={(event) => onSelectJob(job.job_id, event.currentTarget)}
                          className={[
                            "group min-w-36 rounded-md border bg-surface-2 px-3 py-2 text-left",
                            "transition-colors ease-chrome hover:border-ink-muted active:bg-surface-1",
                            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten",
                            selected ? "border-tungsten ring-1 ring-tungsten" : "border-line",
                            job.cost_micros !== undefined ? "border-r-2 border-r-tungsten" : "",
                          ].join(" ")}
                        >
                          <span className={`block font-mono text-xs ${meta.textClass}`}>
                            <span aria-hidden className="mr-2">{meta.glyph}</span>
                            {meta.term}
                          </span>
                          <span className="mt-1 block truncate font-mono text-xs text-ink">
                            {job.job_id}
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
    </div>
  );
}