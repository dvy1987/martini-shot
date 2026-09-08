import type { Job, Worklist } from "@/types/api";

export type JourneyPhase =
  | "prepare"
  | "ingesting"
  | "mixing"
  | "repairing"
  | "consulting"
  | "planning"
  | "executing"
  | "complete"
  | "attention";

export interface JourneySummary {
  phase: JourneyPhase;
  label: string;
  detail: string;
  completed: number;
  total: number;
  attention: number;
}

export function deriveJourney(jobs: readonly Job[], worklist: Worklist | null): JourneySummary {
  const ingest = jobs.filter((job) => job.station === "ingest");
  const loudness = jobs.filter((job) => job.station === "loudness");
  const pickups = jobs.filter((job) => job.station === "pickups");
  const attentionStatuses = ["fail", "failed", "quarantined", "needs_human", "throttled", "paused"];
  const worklistAttention = worklist?.items.filter((item) => attentionStatuses.includes(item.status)).length ?? 0;
  const jobAttention = jobs.filter((job) => attentionStatuses.includes(job.status)).length;
  const attention = worklist ? worklistAttention : jobAttention;
  const terminal = (rows: readonly Job[]) => rows.length > 0 && rows.every((job) => ["pass", "fail", "quarantined", "needs_human", "throttled"].includes(job.status));
  const done = (rows: readonly Job[]) => rows.filter((job) => job.status === "pass").length;

  if (worklist?.status === "waiting_for_budget" || attention > 0) return { phase: "attention", label: "Needs your attention", detail: "A station stopped with a decision, budget hold, or failure that needs review.", completed: 0, total: worklist?.items.length ?? jobs.length, attention: Math.max(1, attention) };
  if (jobs.length === 0 && !worklist) return { phase: "prepare", label: "Prepare the turnover", detail: "Place clips in story order, then set the envelope.", completed: 0, total: 0, attention: 0 };
  if (worklist?.status === "waiting_for_ingest") return { phase: "ingesting", label: "Checking the clips", detail: "The lab is waiting for every ordered original to pass file validation.", completed: done(ingest), total: ingest.length, attention: 0 };
  if (worklist?.phase === "consulting") {
    const completedLooks = worklist.attendance.filter((note) => note.status !== "empty").length;
    return { phase: "consulting", label: "Stations are looking", detail: "The remaining stations are inspecting the updated clips and writing notes.", completed: completedLooks, total: worklist.attendance.length, attention: 0 };
  }
  if (worklist?.phase === "planning") return { phase: "planning", label: "Choosing what fits", detail: "The orchestrator is pricing and ranking real station proposals against your budget.", completed: 0, total: worklist.attendance.length, attention: 0 };
  if (worklist?.phase === "cleanup") {
    const cleanup = worklist.items.filter((item) => ["loudness", "pickups"].includes(item.station));
    const loudnessItems = cleanup.filter((item) => item.station === "loudness");
    const pickupsItems = cleanup.filter((item) => item.station === "pickups");
    if (loudnessItems.some((item) => item.status !== "passed")) return { phase: "mixing", label: "Mixing every clip", detail: "Loudness is measured and mixed before picture repairs can begin.", completed: loudnessItems.filter((item) => item.status === "passed").length, total: loudnessItems.length, attention: 0 };
    return { phase: "repairing", label: "Repairing picture", detail: "Pickups are running on the mixed clips. Originals remain untouched.", completed: pickupsItems.filter((item) => item.status === "passed").length, total: pickupsItems.length, attention: 0 };
  }
  if (!terminal(ingest)) return { phase: "ingesting", label: "Checking the clips", detail: "The lab is verifying the ordered originals before any finishing work begins.", completed: done(ingest), total: ingest.length, attention: 0 };
  if (!terminal(loudness)) return { phase: "mixing", label: "Mixing every clip", detail: "Loudness is measured and mixed before picture repairs can begin.", completed: done(loudness), total: loudness.length, attention: 0 };
  if (!terminal(pickups)) return { phase: "repairing", label: "Repairing picture", detail: "Pickups are running on the mixed clips. Originals remain untouched.", completed: done(pickups), total: pickups.length, attention: 0 };
  if (worklist?.status === "inspecting") return { phase: "consulting", label: "Stations are looking", detail: "The remaining stations are inspecting the updated clips and writing notes.", completed: worklist.attendance.length, total: worklist.attendance.length, attention: 0 };
  if (worklist?.status === "ranking" || worklist?.status === "planning") return { phase: "planning", label: "Choosing what fits", detail: "The orchestrator is pricing and ranking real station proposals against your budget.", completed: 0, total: worklist.attendance.length, attention: 0 };
  if (worklist?.items.some((item) => ["waiting", "queued", "running"].includes(item.status))) {
    const passed = worklist.items.filter((item) => item.status === "passed").length;
    return { phase: "executing", label: "Finishing the handoff", detail: "Approved work is running in the order chosen by the orchestrator.", completed: passed, total: worklist.items.length, attention: 0 };
  }
  if (worklist && worklist.items.length > 0) return { phase: "complete", label: "Ready for handoff", detail: "The run has a recorded result. Inspect the worklist and morning report for the evidence.", completed: worklist.items.filter((item) => item.status === "passed").length, total: worklist.items.length, attention: 0 };
  return { phase: "prepare", label: "Ready when you are", detail: "Order clips and start a finishing run to give the lab its brief.", completed: 0, total: 0, attention: 0 };
}
