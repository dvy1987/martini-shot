import { INGEST_WATCH_DESCRIPTION, stationDescription } from "@/lib/stations";
import type { Job, Worklist } from "@/types/api";

export type JourneyPhase =
  | "prepare"
  | "uploading"
  | "uploaded"
  | "watching"
  | "mixing"
  | "repairing"
  | "consulting"
  | "planning"
  | "executing"
  | "delivering"
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

export const PROGRESS_STAGES: ReadonlyArray<{
  phase: Exclude<JourneyPhase, "prepare" | "uploaded" | "complete" | "attention">;
  name: string;
  description: string;
}> = [
  { phase: "uploading", name: "Upload", description: stationDescription("upload") },
  { phase: "watching", name: "Ingest", description: INGEST_WATCH_DESCRIPTION },
  { phase: "mixing", name: "Fix audio", description: stationDescription("loudness") },
  { phase: "repairing", name: "Pickups", description: stationDescription("pickups") },
  {
    phase: "consulting",
    name: "Review clips",
    description: "Specialist agents look at the updated clips and suggest what still needs work.",
  },
  {
    phase: "planning",
    name: "Plan work",
    description: "Martini Shot ranks the leftover suggestions against the budget.",
  },
  {
    phase: "executing",
    name: "Execute",
    description: "The ranked jobs that still fit the envelope are running.",
  },
  {
    phase: "delivering",
    name: "Delivery",
    description: "We check the finished clips against delivery rules. This always runs last.",
  },
];

export function progressStageIndex(phase: JourneyPhase): number {
  if (phase === "complete") return PROGRESS_STAGES.length;
  if (phase === "uploaded") return 1;
  if (phase === "prepare" || phase === "attention") return 0;
  return PROGRESS_STAGES.findIndex((stage) => stage.phase === phase);
}

export function deriveJourney(jobs: readonly Job[], worklist: Worklist | null): JourneySummary {
  const ingest = jobs.filter((job) => job.station === "ingest");
  const loudness = jobs.filter((job) => job.station === "loudness");
  const pickups = jobs.filter((job) => job.station === "pickups");
  const attentionStatuses = ["fail", "failed", "quarantined", "needs_human", "throttled", "paused"];
  const worklistAttention = worklist?.items.filter((item) => attentionStatuses.includes(item.status)).length ?? 0;
  const jobAttention = jobs.filter((job) => attentionStatuses.includes(job.status)).length;
  const attention = worklist ? worklistAttention : jobAttention;
  const terminal = (rows: readonly Job[]) =>
    rows.length > 0 && rows.every((job) => ["pass", "fail", "quarantined", "needs_human", "throttled"].includes(job.status));
  const done = (rows: readonly Job[]) => rows.filter((job) => job.status === "pass").length;

  if (worklist?.status === "waiting_for_budget" || attention > 0) {
    return {
      phase: "attention",
      label: "Needs your attention",
      detail: "A file or finishing job needs your attention before the run can continue.",
      completed: 0,
      total: worklist?.items.length ?? jobs.length,
      attention: Math.max(1, attention),
    };
  }
  if (jobs.length === 0 && !worklist) {
    return {
      phase: "prepare",
      label: "Get started",
      detail: "Choose your clips in order and set a budget to start.",
      completed: 0,
      total: 0,
      attention: 0,
    };
  }
  if (worklist?.status === "waiting_for_ingest" || !terminal(ingest)) {
    return {
      phase: "uploading",
      label: "Upload",
      detail: stationDescription("upload"),
      completed: done(ingest),
      total: ingest.length,
      attention: 0,
    };
  }
  const cleanupQueued = (worklist?.items ?? []).some((item) =>
    ["loudness", "pickups"].includes(item.station),
  );
  if (
    (worklist?.status === "inspecting" || worklist?.status === "running") &&
    loudness.length === 0 &&
    !cleanupQueued
  ) {
    return {
      phase: "watching",
      label: "Ingest",
      detail: INGEST_WATCH_DESCRIPTION,
      completed: 0,
      total: ingest.length,
      attention: 0,
    };
  }
  if (worklist?.phase === "consulting") {
    const completedLooks = worklist.attendance.filter((note) => note.status !== "empty").length;
    return {
      phase: "consulting",
      label: "Reviewing your clips",
      detail: "The finishing agents are checking the updated clips and suggesting useful improvements.",
      completed: completedLooks,
      total: worklist.attendance.length,
      attention: 0,
    };
  }
  if (worklist?.phase === "planning") {
    return {
      phase: "planning",
      label: "Plan work",
      detail: "Martini Shot is comparing suggested improvements with your budget and choosing what to run.",
      completed: 0,
      total: worklist.attendance.length,
      attention: 0,
    };
  }
  if (worklist?.phase === "cleanup") {
    const cleanup = worklist.items.filter((item) => ["loudness", "pickups"].includes(item.station));
    const loudnessItems = cleanup.filter((item) => item.station === "loudness");
    const pickupsItems = cleanup.filter((item) => item.station === "pickups");
    if (loudnessItems.some((item) => item.status !== "passed")) {
      return {
        phase: "mixing",
        label: "Fix audio",
        detail: stationDescription("loudness"),
        completed: loudnessItems.filter((item) => item.status === "passed").length,
        total: loudnessItems.length,
        attention: 0,
      };
    }
    return {
      phase: "repairing",
      label: "Pickups",
      detail: stationDescription("pickups"),
      completed: pickupsItems.filter((item) => item.status === "passed").length,
      total: pickupsItems.length,
      attention: 0,
    };
  }
  if (loudness.length > 0 && !terminal(loudness)) {
    return {
      phase: "mixing",
      label: "Fix audio",
      detail: stationDescription("loudness"),
      completed: done(loudness),
      total: loudness.length,
      attention: 0,
    };
  }
  if (pickups.length > 0 && !terminal(pickups)) {
    return {
      phase: "repairing",
      label: "Pickups",
      detail: stationDescription("pickups"),
      completed: done(pickups),
      total: pickups.length,
      attention: 0,
    };
  }
  if (worklist?.status === "inspecting") {
    return {
      phase: "consulting",
      label: "Reviewing your clips",
      detail: "The finishing agents are checking the updated clips and suggesting useful improvements.",
      completed: worklist.attendance.length,
      total: worklist.attendance.length,
      attention: 0,
    };
  }
  if (worklist?.status === "ranking" || worklist?.status === "planning") {
    return {
      phase: "planning",
      label: "Plan work",
      detail: "Martini Shot is comparing suggested improvements with your budget and choosing what to run.",
      completed: 0,
      total: worklist.attendance.length,
      attention: 0,
    };
  }
  const activeItems = (worklist?.items ?? []).filter((item) =>
    ["waiting", "queued", "running"].includes(item.status),
  );
  const leftoverActive = activeItems.filter((item) => item.station !== "delivery");
  const deliveryActive = activeItems.filter((item) => item.station === "delivery");
  if (leftoverActive.length > 0) {
    const passed = worklist?.items.filter((item) => item.status === "passed").length ?? 0;
    return {
      phase: "executing",
      label: "Execute",
      detail: "The selected improvements are running in priority order.",
      completed: passed,
      total: worklist?.items.length ?? leftoverActive.length,
      attention: 0,
    };
  }
  if (deliveryActive.length > 0) {
    const passed = worklist?.items.filter((item) => item.station === "delivery" && item.status === "passed").length ?? 0;
    return {
      phase: "delivering",
      label: "Delivery",
      detail: "We check the finished clips against delivery rules. This always runs last.",
      completed: passed,
      total: worklist?.items.filter((item) => item.station === "delivery").length ?? deliveryActive.length,
      attention: 0,
    };
  }
  if (worklist && worklist.items.length > 0) {
    return {
      phase: "complete",
      label: "Run complete",
      detail: "The run is complete. Review the results below and open any finished clips or reports.",
      completed: worklist.items.filter((item) => item.status === "passed").length,
      total: worklist.items.length,
      attention: 0,
    };
  }
  if (terminal(ingest) && !worklist) {
    return {
      phase: "uploaded",
      label: "Upload complete",
      detail: "The files opened and passed the check. Call wrap so Gemini can watch each clip and write the script and scene.",
      completed: done(ingest),
      total: ingest.length,
      attention: 0,
    };
  }
  return {
    phase: "prepare",
    label: "Ready to start",
    detail: "Choose clips in order, set a budget, and call wrap.",
    completed: 0,
    total: 0,
    attention: 0,
  };
}
