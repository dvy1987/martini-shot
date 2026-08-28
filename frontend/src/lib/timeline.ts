import { isJobStatus } from "@/lib/status";
import type { Job, JobStatus, SseEvent } from "@/types/api";

export interface TimelineLane {
  station: string;
  jobs: Job[];
}

const STATUS_ORDER: Record<JobStatus, number> = {
  running: 0,
  needs_human: 1,
  fail: 2,
  quarantined: 3,
  throttled: 4,
  pass: 5,
  queued: 6,
};

function compareJobs(left: Job, right: Job): number {
  const statusDifference = STATUS_ORDER[left.status] - STATUS_ORDER[right.status];
  return statusDifference || left.job_id.localeCompare(right.job_id);
}

export function groupJobsByStation(jobs: readonly Job[]): TimelineLane[] {
  const lanes = new Map<string, Job[]>();

  for (const currentJob of jobs) {
    const stationJobs = lanes.get(currentJob.station);
    if (stationJobs) {
      stationJobs.push(currentJob);
    } else {
      lanes.set(currentJob.station, [currentJob]);
    }
  }

  return [...lanes.entries()]
    .sort(([leftStation], [rightStation]) => leftStation.localeCompare(rightStation))
    .map(([station, stationJobs]) => ({
      station,
      jobs: [...stationJobs].sort(compareJobs),
    }));
}

export function upsertJob(jobs: readonly Job[], updatedJob: Job): Job[] {
  const existingIndex = jobs.findIndex(({ job_id }) => job_id === updatedJob.job_id);
  if (existingIndex === -1) return [...jobs, updatedJob];
  return jobs.map((job, index) => (index === existingIndex ? updatedJob : job));
}

function isJob(value: unknown): value is Job {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Job>;
  return (
    typeof candidate.job_id === "string" &&
    typeof candidate.station === "string" &&
    typeof candidate.project_id === "string" &&
    Array.isArray(candidate.input_refs) &&
    candidate.input_refs.every((reference) => typeof reference === "string") &&
    typeof candidate.status === "string" &&
    isJobStatus(candidate.status) &&
    typeof candidate.attempts === "number"
  );
}

export function jobFromSseEvent(event: SseEvent): Job | null {
  if (event.type !== "job.updated" || !event.payload || typeof event.payload !== "object") {
    return null;
  }
  const job = (event.payload as { job?: unknown }).job;
  return isJob(job) ? job : null;
}