import { stationRank } from "@/lib/stations";
import type { Job, JobClip, JobStatus } from "@/types/api";

export type AfterState = "pending" | "no_change" | "clip";
export type BeforeState = "none" | "clip";

const PENDING: ReadonlySet<JobStatus> = new Set(["queued", "running"]);
const BLOCKED: ReadonlySet<JobStatus> = new Set(["fail", "quarantined", "needs_human", "throttled"]);

export interface BoardRow {
  id: string;
  job: Job;
  displayStation: string;
  displayStatus: JobStatus;
  before: BeforeState;
  after: AfterState;
  afterSide: "before" | "after";
}

export interface BoardLane {
  station: string;
  rows: BoardRow[];
}

export function clipName(job: Pick<Job, "job_id" | "input_refs">): string {
  const ref = job.input_refs[0] ?? "";
  const name = ref.replaceAll("\\", "/").split("/").pop() ?? "";
  return name || job.job_id;
}

export function afterState(job: Job): AfterState {
  if (PENDING.has(job.status)) return "pending";
  const result = job.result ?? {};
  const before = job.input_refs[0] ?? "";
  const artifact = typeof result.artifact_ref === "string" ? result.artifact_ref : "";
  if (artifact && artifact !== before) return "clip";
  if (hasClipMetadata(result)) return "clip";
  return "no_change";
}

export function boardRows(jobs: readonly Job[]): BoardRow[] {
  const rows: BoardRow[] = [];
  for (const job of jobs) {
    if (job.station === "ingest") {
      rows.push({
        id: `upload:${job.job_id}`,
        job,
        displayStation: "upload",
        displayStatus: job.status,
        before: "none",
        after: uploadAfter(job),
        afterSide: "before",
      });
      rows.push({
        id: `ingest:${job.job_id}`,
        job,
        displayStation: "ingest",
        displayStatus: ingestWatchStatus(job, jobs),
        before: job.input_refs[0] ? "clip" : "none",
        after: ingestWatchAfter(job, jobs),
        afterSide: "after",
      });
      continue;
    }
    rows.push({
      id: `${job.station}:${job.job_id}`,
      job,
      displayStation: job.station,
      displayStatus: job.status,
      before: job.input_refs[0] ? "clip" : "none",
      after: afterState(job),
      afterSide: "after",
    });
  }
  return rows;
}

export function groupBoardLanes(jobs: readonly Job[]): BoardLane[] {
  const lanes = new Map<string, BoardRow[]>();
  for (const row of boardRows(jobs)) {
    const existing = lanes.get(row.displayStation);
    if (existing) existing.push(row);
    else lanes.set(row.displayStation, [row]);
  }
  return [...lanes.entries()]
    .sort(([left], [right]) => {
      const rank = stationRank(left) - stationRank(right);
      return rank || left.localeCompare(right);
    })
    .map(([station, stationRows]) => ({
      station,
      rows: [...stationRows].sort(compareBoardRows),
    }));
}

function uploadAfter(job: Job): AfterState {
  if (PENDING.has(job.status)) return "pending";
  return job.input_refs[0] ? "clip" : "no_change";
}

function ingestWatchStatus(job: Job, jobs: readonly Job[]): JobStatus {
  if (PENDING.has(job.status)) return "queued";
  if (watchComplete(job, jobs)) return "pass";
  if (BLOCKED.has(job.status)) return job.status;
  return "running";
}

function ingestWatchAfter(job: Job, jobs: readonly Job[]): AfterState {
  if (PENDING.has(job.status)) return "pending";
  if (watchComplete(job, jobs)) return "clip";
  if (BLOCKED.has(job.status)) return "no_change";
  return "pending";
}

function watchComplete(job: Job, jobs: readonly Job[]): boolean {
  if (hasWatchNotes(job.result)) return true;
  const origin = job.input_refs[0];
  if (!origin) return false;
  return jobs.some(
    (other) =>
      other.job_id !== job.job_id &&
      hasWatchNotes(other.result) &&
      clipSharesOrigin(origin, job.job_id, other.input_refs[0] ?? ""),
  );
}

function clipSharesOrigin(origin: string, ingestJobId: string, otherRef: string): boolean {
  if (otherRef === origin) return true;
  const marker = `/ingest/${ingestJobId}/`;
  return origin.includes(marker) && otherRef.includes(marker);
}

function hasWatchNotes(result: Record<string, unknown> | undefined): boolean {
  if (!result) return false;
  if (result.ingested === true) return true;
  if (typeof result.spoken_words === "string") return true;
  if (typeof result.scene === "string" && result.scene) return true;
  if (result.scene_understanding && typeof result.scene_understanding === "object") return true;
  const handoff = result.handoff;
  return Boolean(handoff && typeof handoff === "object" && "scene" in handoff);
}

export function watchNotesFromJobs(job: Job, jobs: readonly Job[]): Record<string, unknown> {
  const origin = job.input_refs[0] ?? "";
  const notes: Record<string, unknown> = {};
  const related = [job, ...jobs.filter((other) => other.job_id !== job.job_id)];
  for (const candidate of related) {
    if (origin && !clipSharesOrigin(origin, job.job_id, candidate.input_refs[0] ?? "")) {
      continue;
    }
    mergeWatchNote(notes, candidate.result ?? {});
  }
  return notes;
}

export function withWatchNotes(clip: JobClip, job: Job, jobs: readonly Job[]): JobClip {
  const extra = watchNotesFromJobs(job, jobs);
  const filled = Object.fromEntries(
    Object.entries(clip.metadata).filter(([, value]) => value != null && value !== ""),
  );
  return {
    ...clip,
    metadata: { ...extra, ...filled },
  };
}

function mergeWatchNote(target: Record<string, unknown>, source: Record<string, unknown>): void {
  const nested =
    source.scene_understanding && typeof source.scene_understanding === "object"
      ? (source.scene_understanding as Record<string, unknown>)
      : {};
  const scene = source.scene || nested.scene;
  const spoken = source.spoken_words || nested.spoken_words;
  if (typeof scene === "string" && scene && !target.scene) target.scene = scene;
  if (typeof spoken === "string" && spoken && !target.spoken_words) target.spoken_words = spoken;
}

function hasClipMetadata(result: Record<string, unknown>): boolean {
  const probe = result.probe;
  if (probe && typeof probe === "object") return true;
  return hasWatchNotes(result);
}

function compareBoardRows(left: BoardRow, right: BoardRow): number {
  const order: Record<JobStatus, number> = {
    running: 0,
    needs_human: 1,
    fail: 2,
    quarantined: 3,
    throttled: 4,
    pass: 5,
    queued: 6,
  };
  const statusDifference = order[left.displayStatus] - order[right.displayStatus];
  return statusDifference || left.job.job_id.localeCompare(right.job.job_id);
}
