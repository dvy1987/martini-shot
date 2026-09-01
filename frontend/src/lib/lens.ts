import type { Job, JobStatus } from "@/types/api";

/** Empty selection means no filter — show the full observed set. */
export function filterJobsByStatus(
  jobs: readonly Job[],
  statuses: ReadonlySet<JobStatus>,
): Job[] {
  if (statuses.size === 0) return [...jobs];
  return jobs.filter((job) => statuses.has(job.status));
}

export function toggleStatus(
  statuses: ReadonlySet<JobStatus>,
  status: JobStatus,
): Set<JobStatus> {
  const next = new Set(statuses);
  if (next.has(status)) next.delete(status);
  else next.add(status);
  return next;
}
