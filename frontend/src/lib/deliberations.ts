/** H-1f client logic: deliberation cache upserts, dissent lookup, SSE extraction. */

import type { Deliberation, SseEvent } from "@/types/api";

export function upsertDeliberation(
  rows: readonly Deliberation[],
  record: Deliberation,
): Deliberation[] {
  const existingIndex = rows.findIndex(({ cycle_id }) => cycle_id === record.cycle_id);
  if (existingIndex === -1) return [...rows, record];
  return rows.map((row, index) => (index === existingIndex ? record : row));
}

/** Dissent lines from the newest deliberation for a job (empty when none). */
export function dissentForJob(
  rows: readonly Deliberation[],
  jobId: string,
): string[] {
  const forJob = rows
    .filter((row) => row.trigger.job_id === jobId)
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
  return forJob[0]?.recommendation.dissent ?? [];
}

function isDeliberation(value: unknown): value is Deliberation {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Deliberation>;
  return (
    typeof candidate.cycle_id === "string" &&
    typeof candidate.case_id === "string" &&
    typeof candidate.created_at === "string" &&
    Array.isArray(candidate.specialists) &&
    typeof candidate.recommendation === "object" &&
    candidate.recommendation !== null &&
    typeof candidate.status === "string"
  );
}

export function deliberationFromSseEvent(event: SseEvent): Deliberation | null {
  if (
    event.type !== "deliberation.completed" ||
    !event.payload ||
    typeof event.payload !== "object"
  ) {
    return null;
  }
  return isDeliberation(event.payload) ? event.payload : null;
}
