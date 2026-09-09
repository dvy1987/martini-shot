/** Operator-facing reading of a run-pulse snapshot. Grafana stays off-screen. */

import { cost } from "@/lib/formatters";
import { stationName } from "@/lib/stations";
import type { FactoryVerdict, RunPulse, RunPulseJob, RunPulseWheelItem } from "@/types/api";

export interface BriefingSection {
  id: "health" | "spend" | "time" | "actions";
  title: string;
  meaning: string;
  detail: string;
  tone: "ok" | "warn" | "muted";
}

export interface BriefingAction {
  kind: string;
  label: string;
  text: string;
  jobId?: string | null;
}

export interface JobTally {
  total: number;
  passed: number;
  blocked: number;
  working: number;
}

export interface RunBriefing {
  title: string;
  sourceLine: string;
  healthConfirmed: boolean;
  sections: BriefingSection[];
  actions: BriefingAction[];
  tally: JobTally;
}

const BLOCKED = new Set(["fail", "failed", "quarantined", "needs_human", "throttled"]);
const WORKING = new Set(["queued", "running", "leased"]);

export function tallyJobs(jobs: readonly RunPulseJob[] | undefined): JobTally {
  const rows = jobs ?? [];
  return {
    total: rows.length,
    passed: rows.filter((row) => row.status === "pass").length,
    blocked: rows.filter((row) => BLOCKED.has(row.status)).length,
    working: rows.filter((row) => WORKING.has(row.status)).length,
  };
}

export function explainWheelItem(item: RunPulseWheelItem): BriefingAction {
  const kind = item.kind || "note";
  const labels: Record<string, string> = {
    spend: "Budget stop",
    fallback: "Model fallback",
    human: "Needs you",
    intervention: "Supervisor look",
    note: "Note",
  };
  return {
    kind,
    label: labels[kind] ?? "Note",
    text: explainWheelText(kind, item.text),
    jobId: item.job_id,
  };
}

export function buildRunBriefing(pulse: RunPulse): RunBriefing {
  const tally = tallyJobs(pulse.jobs);
  const healthConfirmed = pulse.grafana === "ok";
  return {
    title: "This run",
    sourceLine: healthConfirmed
      ? "Health, spend, and time left for this show — read here, not in another tool."
      : "House-wide health could not be confirmed. Spend and jobs below are still from this show.",
    healthConfirmed,
    sections: [
      explainHealth(pulse.factory.verdict, pulse.factory.headline, tally),
      explainSpend(pulse),
      explainTime(pulse),
      explainActions(pulse, tally),
    ],
    actions: pulse.wheel.items.map(explainWheelItem),
    tally,
  };
}

function explainHealth(
  verdict: FactoryVerdict,
  headline: string,
  tally: JobTally,
): BriefingSection {
  if (verdict === "degraded") {
    return {
      id: "health",
      title: "House health",
      meaning: "Failures are showing up across shows, not only this one.",
      detail: "This is a house problem. Jobs on Timeline that need you are not a one-off clip glitch.",
      tone: "warn",
    };
  }
  if (verdict === "unknown") {
    return {
      id: "health",
      title: "House health",
      meaning: "We could not confirm whether other shows are failing too.",
      detail:
        tally.blocked > 0
          ? `${tally.blocked} job${tally.blocked === 1 ? "" : "s"} on this show still need attention on Timeline.`
          : "Spend and the job list below are still from this show.",
      tone: "muted",
    };
  }
  if (headline.toLowerCase().includes("this dump is failing")) {
    return {
      id: "health",
      title: "House health",
      meaning: "Other shows look fine. This show has failures.",
      detail: "Open Timeline for the jobs that need you. The rest of the house is not the issue.",
      tone: "warn",
    };
  }
  return {
    id: "health",
    title: "House health",
    meaning: "The house is running normally.",
    detail:
      tally.blocked > 0
        ? `${tally.blocked} job${tally.blocked === 1 ? "" : "s"} on this show still need a look on Timeline.`
        : tally.total === 0
          ? "No jobs have run on this show yet."
          : `${tally.passed} of ${tally.total} jobs on this show have passed.`,
    tone: tally.blocked > 0 ? "warn" : "ok",
  };
}

function explainSpend(pulse: RunPulse): BriefingSection {
  const top = pulse.burn.top[0];
  if (!top) {
    return {
      id: "spend",
      title: "Spend",
      meaning: "What this show has actually billed.",
      detail: "Nothing on this show has billed yet.",
      tone: "muted",
    };
  }
  const stage = stationName(top.station);
  const extras = pulse.burn.top
    .slice(1)
    .map((row) => `${stationName(row.station)} ${cost(row.cost_micros)}`)
    .join("; ");
  return {
    id: "spend",
    title: "Spend",
    meaning: "What this show has actually billed.",
    detail: extras
      ? `${stage} is the expensive step (${cost(top.cost_micros)}): ${top.why}. Also billed: ${extras}.`
      : `${stage} is the expensive step (${cost(top.cost_micros)}): ${top.why}.`,
    tone: "ok",
  };
}

function explainTime(pulse: RunPulse): BriefingSection {
  if (pulse.eta.remaining_items === 0) {
    return {
      id: "time",
      title: "Time left",
      meaning: "Queued finishing work still waiting.",
      detail: "No finishing work is waiting. The run can be reviewed as-is.",
      tone: "ok",
    };
  }
  if (pulse.eta.eta_seconds == null) {
    return {
      id: "time",
      title: "Time left",
      meaning: "Queued finishing work still waiting.",
      detail: `${pulse.eta.remaining_items} item${pulse.eta.remaining_items === 1 ? "" : "s"} still in the work plan. Typical duration for those stages is not available yet.`,
      tone: "muted",
    };
  }
  return {
    id: "time",
    title: "Time left",
    meaning: "Queued finishing work still waiting.",
    detail: pulse.eta.headline.replace("dump", "show"),
    tone: "ok",
  };
}

function explainActions(pulse: RunPulse, tally: JobTally): BriefingSection {
  const count = pulse.wheel.items.length;
  if (count === 0) {
    return {
      id: "actions",
      title: "What already ran on its own",
      meaning: "Stops, fallbacks, and supervisor looks recorded for this show.",
      detail:
        tally.working > 0
          ? `${tally.working} job${tally.working === 1 ? " is" : "s are"} still running. No automatic stops or fallbacks have been recorded yet.`
          : "No automatic stops, fallbacks, or supervisor looks have been recorded yet.",
      tone: "muted",
    };
  }
  return {
    id: "actions",
    title: "What already ran on its own",
    meaning: "Stops, fallbacks, and supervisor looks recorded for this show.",
    detail: `${count} automatic action${count === 1 ? "" : "s"} recorded. Read each one below — you do not need another board to understand them.`,
    tone: "ok",
  };
}

function explainWheelText(kind: string, raw: string): string {
  const cleaned = raw.replace(/\s*job_id=\S+/g, "").replace(/\s+/g, " ").trim();
  if (kind === "spend") {
    return cleaned
      ? `Stopped work that was burning the budget. ${cleaned}.`
      : "Stopped work that was burning the budget.";
  }
  if (kind === "fallback") {
    return "Omni could not finish a clip; Veo completed it so you still have a take.";
  }
  if (kind === "human") {
    return cleaned || "A decision was recorded that needed you.";
  }
  if (kind === "intervention") {
    return cleaned || "The supervisor looked at a failure and recorded a verdict.";
  }
  return cleaned || "A note was recorded on this run.";
}
