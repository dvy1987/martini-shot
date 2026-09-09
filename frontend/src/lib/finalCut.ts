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

function originOf(job: Job): string {
  return job.input_refs[0] ?? "";
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

function jobsForOrigin(jobs: readonly Job[], origin: string): Job[] {
  return jobs.filter((job) => originOf(job) === origin);
}

export function defaultFinalCutPick(
  jobs: readonly Job[],
  origin: string,
): FinalCutPick | null {
  const rows = boardRows(jobsForOrigin(jobs, origin)).filter(
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
): FinalCutPick | null {
  if (!ready) return null;
  if (override) {
    const job = jobsForOrigin(jobs, origin).find((row) => row.job_id === override.jobId);
    if (job) return override;
  }
  return defaultFinalCutPick(jobs, origin);
}

export function finalCutSlots(
  jobs: readonly Job[],
  overrides: Readonly<Record<string, FinalCutPick>>,
  worklist: Worklist | null | undefined = null,
): FinalCutSlot[] {
  const ready = orchestratorHasStopped(worklist);
  return sequenceOrigins(jobs).map((origin) => {
    const ingest = jobsForOrigin(jobs, origin).find((job) => job.station === "ingest");
    return {
      origin,
      name: ingest ? clipName(ingest) : origin,
      pick: resolveFinalCutPick(jobs, origin, overrides[origin], ready),
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
  playlist: readonly FinalCutPick[],
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
