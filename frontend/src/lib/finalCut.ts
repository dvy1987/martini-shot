/** Final cut: one slot per original clip. Fills with last successful After when the orchestrator stops. */

import { boardRows, clipName, type BoardRow } from "@/lib/clipDisplay";
import { stationRank } from "@/lib/stations";
import type { Job, Worklist } from "@/types/api";

export interface FinalCutPick {
  jobId: string;
  side: "before" | "after";
}

export interface FinalCutSlot {
  origin: string;
  name: string;
  pick: FinalCutPick | null;
}

export type FinalCutAction = "Final Cut" | "Add to final cut";

export interface FinalCutSource extends FinalCutPick {
  name: string;
}

export interface FinalCutDownload {
  getClip: (jobId: string, side: "before" | "after") => Promise<{ url: string }>;
  fetchBlob: (url: string) => Promise<Blob>;
  toObjectUrl: (blob: Blob) => string;
}

const BUSY_STATUS = new Set([
  "inspecting",
  "ranking",
  "planning",
  "running",
  "waiting_for_ingest",
]);

function originOf(job: Pick<Job, "input_refs">): string {
  return job.input_refs[0] ?? "";
}
function shotIdOf(job: Pick<Job, "job_id" | "result">, worklist?: Worklist | null): string {
  if (typeof job.result?.shot_id === "string" && job.result.shot_id) {
    return job.result.shot_id;
  }
  return worklist?.items.find((item) => item.job_id === job.job_id)?.shot_id ?? "";
}

function originByShot(
  jobs: readonly Job[],
  worklist?: Worklist | null,
): Map<string, string> {
  const origins = new Map<string, string>();
  for (const [shotId, origin] of Object.entries(worklist?.source_by_shot ?? {})) {
    if (shotId && origin) origins.set(shotId, origin);
  }
  for (const job of jobs) {
    if (job.station !== "ingest") continue;
    const shotId = shotIdOf(job, worklist);
    const origin = originOf(job);
    if (shotId && origin) origins.set(shotId, origin);
  }
  return origins;
}

function uploadIndex(job: Job): number {
  const raw = job.result?.upload_index;
  return typeof raw === "number" && Number.isFinite(raw) ? raw : Number.POSITIVE_INFINITY;
}

export function orchestratorHasStopped(worklist: Worklist | null | undefined): boolean {
  if (!worklist) return false;
  return !BUSY_STATUS.has(worklist.status);
}

export function sequenceOrigins(jobs: readonly Job[]): string[] {
  const ingest = jobs.filter((job) => job.station === "ingest" && originOf(job));
  ingest.sort((left, right) => {
    const order = uploadIndex(left) - uploadIndex(right);
    return order || left.job_id.localeCompare(right.job_id);
  });
  const seen = new Set<string>();
  const origins: string[] = [];
  for (const job of ingest) {
    const origin = originOf(job);
    if (seen.has(origin)) continue;
    seen.add(origin);
    origins.push(origin);
  }
  return origins;
}

function ingestFolder(ref: string): string {
  const parts = ref.replaceAll("\\", "/").split("/");
  const at = parts.indexOf("ingest");
  if (at >= 0 && parts[at + 1]) {
    return parts.slice(0, at + 2).join("/");
  }
  return ref.replaceAll("\\", "/");
}

export function originKey(
  job: Pick<Job, "job_id" | "station" | "input_refs" | "result">,
  jobs: readonly Job[],
  worklist?: Worklist | null,
): string {
  const ref = originOf(job);
  const shotOrigin = originByShot(jobs, worklist).get(shotIdOf(job, worklist));
  if (shotOrigin) return shotOrigin;
  const origins = sequenceOrigins(jobs);
  if (ref && origins.includes(ref)) return ref;
  if (ref) {
    const folder = ingestFolder(ref);
    const match = origins.find((origin) => ingestFolder(origin) === folder);
    if (match) return match;
  }
  if (job.station === "ingest") return ref || `job:${job.job_id}`;
  const ingest = jobs.filter((row) => row.station === "ingest");
  const onlyIngest = ingest[0];
  if (ingest.length === 1 && onlyIngest) return originKey(onlyIngest, jobs, worklist);
  return ref || `job:${job.job_id}`;
}

export interface ClipJourney {
  origin: string;
  label: string;
  rows: BoardRow[];
}

export function groupBoardByClip(
  jobs: readonly Job[],
  worklist?: Worklist | null,
): ClipJourney[] {
  const origins = sequenceOrigins(jobs);
  const buckets = new Map<string, BoardRow[]>();
  const order: string[] = [...origins];
  for (const row of boardRows(jobs)) {
    const key = originKey(row.job, jobs, worklist);
    const existing = buckets.get(key);
    if (existing) existing.push(row);
    else {
      buckets.set(key, [row]);
      if (!order.includes(key)) order.push(key);
    }
  }
  return order
    .filter((origin) => buckets.has(origin))
    .map((origin, index) => ({
      origin,
      label: `Clip ${index + 1}`,
      rows: [...(buckets.get(origin) ?? [])].sort(
        (left, right) =>
          stationRank(left.displayStation) - stationRank(right.displayStation) ||
          left.job.job_id.localeCompare(right.job.job_id),
      ),
    }));
}

function jobsForOrigin(
  jobs: readonly Job[],
  origin: string,
  worklist?: Worklist | null,
): Job[] {
  return jobs.filter((job) => originKey(job, jobs, worklist) === origin);
}

export function defaultFinalCutPick(
  jobs: readonly Job[],
  origin: string,
  worklist?: Worklist | null,
): FinalCutPick | null {
  const rows = boardRows(jobsForOrigin(jobs, origin, worklist)).filter(
    (row) => row.after === "clip" && row.job.status === "pass",
  );
  if (rows.length === 0) return null;
  const chosen = [...rows].sort(
    (left, right) => stationRank(left.displayStation) - stationRank(right.displayStation),
  ).at(-1);
  if (!chosen) return null;
  return { jobId: chosen.job.job_id, side: chosen.afterSide };
}

export function applyFinalCutPick(
  overrides: Readonly<Record<string, FinalCutPick>>,
  origin: string,
  pick: FinalCutPick,
): Record<string, FinalCutPick> {
  return { ...overrides, [origin]: pick };
}

export function resolveFinalCutPick(
  jobs: readonly Job[],
  origin: string,
  override: FinalCutPick | undefined,
  ready: boolean,
  worklist?: Worklist | null,
): FinalCutPick | null {
  if (!ready) return null;
  if (override) {
    const job = jobsForOrigin(jobs, origin, worklist).find(
      (row) => row.job_id === override.jobId,
    );
    if (job) return override;
  }
  return defaultFinalCutPick(jobs, origin, worklist);
}

export function finalCutSlots(
  jobs: readonly Job[],
  overrides: Readonly<Record<string, FinalCutPick>>,
  worklist: Worklist | null | undefined = null,
): FinalCutSlot[] {
  const ready = orchestratorHasStopped(worklist);
  return sequenceOrigins(jobs).map((origin) => {
    const ingest = jobsForOrigin(jobs, origin, worklist).find(
      (job) => job.station === "ingest",
    );
    return {
      origin,
      name: ingest ? clipName(ingest) : origin,
      pick: resolveFinalCutPick(jobs, origin, overrides[origin], ready, worklist),
    };
  });
}

export function finalCutAction(
  row: BoardRow | undefined,
  pick: FinalCutPick | null,
): FinalCutAction | null {
  if (!row || row.after !== "clip") return null;
  if (!pick) return null;
  if (pick.jobId === row.job.job_id && pick.side === row.afterSide) return "Final Cut";
  return "Add to final cut";
}

export function finalCutPlaylist(slots: readonly FinalCutSlot[]): FinalCutSource[] {
  return slots.flatMap((slot) => (slot.pick ? [{ ...slot.pick, name: slot.name }] : []));
}

export async function downloadFinalCutBlobs(
  playlist: readonly FinalCutSource[],
  load: FinalCutDownload,
): Promise<string[]> {
  const urls: string[] = [];
  for (const item of playlist) {
    const clip = await load.getClip(item.jobId, item.side);
    const blob = await load.fetchBlob(clip.url);
    urls.push(load.toObjectUrl(blob));
  }
  return urls;
}
