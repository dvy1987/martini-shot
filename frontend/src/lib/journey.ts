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

  if (worklist?.status === "waiting_for_budget" || attention > 0) return { phase: "attention", label: "Needs your attention", detail: "A file or finishing job needs your attention before the run can continue.", completed: 0, total: worklist?.items.length ?? jobs.length, attention: Math.max(1, attention) };
  if (jobs.length === 0 && !worklist) return { phase: "prepare", label: "Get started", detail: "Choose your clips in order and set a budget to start.", completed: 0, total: 0, attention: 0 };
  if (worklist?.status === "waiting_for_ingest") return { phase: "ingesting", label: "Checking the clips", detail: "Martini Shot is checking each file before it starts any finishing work.", completed: done(ingest), total: ingest.length, attention: 0 };
  if (worklist?.phase === "consulting") {
    const completedLooks = worklist.attendance.filter((note) => note.status !== "empty").length;
    return { phase: "consulting", label: "Reviewing your clips", detail: "The finishing agents are checking the updated clips and suggesting useful improvements.", completed: completedLooks, total: worklist.attendance.length, attention: 0 };
  }
  if (worklist?.phase === "planning") return { phase: "planning", label: "Choosing improvements", detail: "Martini Shot is comparing suggested improvements with your budget and choosing what to run.", completed: 0, total: worklist.attendance.length, attention: 0 };
  if (worklist?.phase === "cleanup") {
    const cleanup = worklist.items.filter((item) => ["loudness", "pickups"].includes(item.station));
    const loudnessItems = cleanup.filter((item) => item.station === "loudness");
    const pickupsItems = cleanup.filter((item) => item.station === "pickups");
    if (loudnessItems.some((item) => item.status !== "passed")) return { phase: "mixing", label: "Fixing audio", detail: "Martini Shot is checking and balancing the audio in every clip.", completed: loudnessItems.filter((item) => item.status === "passed").length, total: loudnessItems.length, attention: 0 };
    return { phase: "repairing", label: "Checking picture", detail: "Martini Shot is checking every clip for visible picture problems. Your original files stay unchanged.", completed: pickupsItems.filter((item) => item.status === "passed").length, total: pickupsItems.length, attention: 0 };
  }
  if (!terminal(ingest)) return { phase: "ingesting", label: "Checking the clips", detail: "Martini Shot is checking the files in the order you selected.", completed: done(ingest), total: ingest.length, attention: 0 };
  if (!terminal(loudness)) return { phase: "mixing", label: "Fixing audio", detail: "Martini Shot is checking and balancing the audio in every clip.", completed: done(loudness), total: loudness.length, attention: 0 };
  if (!terminal(pickups)) return { phase: "repairing", label: "Checking picture", detail: "Martini Shot is checking every clip for visible picture problems. Your original files stay unchanged.", completed: done(pickups), total: pickups.length, attention: 0 };
  if (worklist?.status === "inspecting") return { phase: "consulting", label: "Reviewing your clips", detail: "The finishing agents are checking the updated clips and suggesting useful improvements.", completed: worklist.attendance.length, total: worklist.attendance.length, attention: 0 };
  if (worklist?.status === "ranking" || worklist?.status === "planning") return { phase: "planning", label: "Choosing improvements", detail: "Martini Shot is comparing suggested improvements with your budget and choosing what to run.", completed: 0, total: worklist.attendance.length, attention: 0 };
  if (worklist?.items.some((item) => ["waiting", "queued", "running"].includes(item.status))) {
    const passed = worklist.items.filter((item) => item.status === "passed").length;
    return { phase: "executing", label: "Finishing the handoff", detail: "The selected improvements are running in priority order.", completed: passed, total: worklist.items.length, attention: 0 };
  }
  if (worklist && worklist.items.length > 0) return { phase: "complete", label: "Run complete", detail: "The run is complete. Review the results below and open any finished clips or reports.", completed: worklist.items.filter((item) => item.status === "passed").length, total: worklist.items.length, attention: 0 };
  return { phase: "prepare", label: "Ready to start", detail: "Choose clips in order, set a budget, and call wrap.", completed: 0, total: 0, attention: 0 };
}
