/** Per-row Retry/Accept in the table view — mirrors the backend's
 * RETRYABLE_STALLED / ACCEPTABLE_STALLED (backend/supervisor/finishing_loop.py).
 * Retry/Accept act on the worklist item's own status, not `job.status` —
 * those use different vocabularies (job: "fail"; worklist item: "failed").
 */
import type { Job, Worklist, WorklistItem } from "@/types/api";

const RETRYABLE_STALLED = new Set(["failed", "paused", "needs_human"]);

// Paused is a budget throttle, not a quality call a human can wave
// through, so it is retryable but never acceptable.
const ACCEPTABLE_STALLED = new Set(["failed", "needs_human"]);

export function worklistItemForJob(
  job: Job,
  worklist: Worklist | null | undefined,
): WorklistItem | null {
  return worklist?.items.find((item) => item.job_id === job.job_id) ?? null;
}

export function canRetryRow(job: Job, worklist: Worklist | null | undefined): boolean {
  const item = worklistItemForJob(job, worklist);
  return Boolean(item && RETRYABLE_STALLED.has(item.status));
}

export function canAcceptRow(job: Job, worklist: Worklist | null | undefined): boolean {
  const item = worklistItemForJob(job, worklist);
  return Boolean(item && ACCEPTABLE_STALLED.has(item.status));
}
