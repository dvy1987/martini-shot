/** Operator-facing reading of a run-pulse snapshot. Grafana stays off-screen. */

import { readAgentNotes } from "@/lib/agentNotes";
import { cost } from "@/lib/formatters";
import { stationName } from "@/lib/stations";
import { buildSuggestionPlan } from "@/lib/suggestionPlan";
import type {
  FactoryVerdict,
  Job,
  JobStatus,
  RunPulse,
  RunPulseJob,
  RunPulseWheelItem,
  Worklist,
} from "@/types/api";

export interface BriefingSection {
  id: "health" | "spend" | "time" | "actions";
  title: string;
  meaning: string;
  detail: string;
  tone: "ok" | "fail" | "muted";
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

export type AttentionLane = "execute" | "delivery";

export interface AttentionItem {
  lane: AttentionLane;
  heading: string;
  clip: string;
  why: string;
  next: string;
  jobId: string;
}

export interface RunBriefing {
  title: string;
  sourceLine: string;
  healthConfirmed: boolean;
  attention: AttentionItem[];
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

export function buildRunBriefing(
  pulse: RunPulse,
  liveJobs?: readonly Job[],
  worklist?: Worklist | null,
): RunBriefing {
  const jobs = jobsForAttention(pulse, liveJobs);
  const tally = tallyFromJobs(jobs, pulse.jobs);
  const healthConfirmed = pulse.grafana === "ok";
  const attention = buildAttention(jobs);
  return {
    title: "This run",
    sourceLine: attentionSourceLine(attention, healthConfirmed),
    healthConfirmed,
    attention,
    sections: [
      explainHealth(pulse.factory.verdict, pulse.factory.headline, tally, attention),
      explainSpend(pulse, worklist),
      explainTime(pulse, tally),
      explainActions(pulse),
    ],
    actions: pulse.wheel.items.map(explainWheelItem),
    tally,
  };
}

function attentionSourceLine(attention: AttentionItem[], healthConfirmed: boolean): string {
  if (attention.length > 0) {
    return "This show needs you. Click House health to read why Execute or Delivery stopped.";
  }
  return healthConfirmed
    ? "Health, spend, and time left for this show — click a heading to read it."
    : "House-wide health could not be confirmed. Spend and jobs below are still from this show.";
}

function tallyFromJobs(jobs: readonly Job[], pulseJobs?: readonly RunPulseJob[]): JobTally {
  if (jobs.length > 0) {
    return {
      total: jobs.length,
      passed: jobs.filter((job) => job.status === "pass").length,
      blocked: jobs.filter((job) => BLOCKED.has(job.status)).length,
      working: jobs.filter((job) => WORKING.has(job.status)).length,
    };
  }
  return tallyJobs(pulseJobs);
}

function jobsForAttention(pulse: RunPulse, liveJobs?: readonly Job[]): Job[] {
  const merged = new Map<string, Job>();
  for (const row of pulse.jobs ?? []) {
    merged.set(row.job_id, pulseJobAsJob(row));
  }
  for (const job of liveJobs ?? []) {
    merged.set(job.job_id, job);
  }
  return [...merged.values()];
}

function pulseJobAsJob(row: RunPulseJob): Job {
  return {
    job_id: row.job_id,
    station: row.station,
    project_id: "",
    input_refs: [row.clip],
    status: (row.status as JobStatus) || "fail",
    attempts: 1,
    cost_micros: row.cost_micros,
    error: row.error ?? null,
    result: row.result ?? {},
  };
}

function buildAttention(jobs: readonly Job[]): AttentionItem[] {
  const items = jobs.filter((job) => BLOCKED.has(job.status)).map(attentionItem);
  return items.sort((left, right) => Number(left.lane === "delivery") - Number(right.lane === "delivery"));
}

function attentionItem(job: Job): AttentionItem {
  const lane: AttentionLane = job.station === "delivery" ? "delivery" : "execute";
  const notes = readAgentNotes(job);
  const why = notes.failed || notes.problem || "This step stopped and still needs a look.";
  const clip = clipName(job);
  return {
    lane,
    heading: lane === "delivery" ? "Delivery" : `Execute · ${stationName(job.station)}`,
    clip,
    why,
    next: nextStep(job, lane, why),
    jobId: job.job_id,
  };
}

function nextStep(job: Job, lane: AttentionLane, why: string): string {
  if (lane === "delivery") {
    return job.status === "needs_human"
      ? "This is a shipment check, not a story call. Open Agent Notes on Timeline. If it is waiting on you, open Decisions."
      : "This is a shipment check. Open Agent Notes on Timeline, then decide whether the clip can ship.";
  }
  if (/only allows/i.test(why)) {
    return "Open Timeline and read Agent Notes on this Execute step. The original clip is still there. A later pass can edit the clip in pieces.";
  }
  return "Open Timeline and read Agent Notes on this Execute step. The original clip is still there.";
}

function clipName(job: Job): string {
  const ref = job.input_refs[0] ?? job.job_id;
  return ref.replace(/\\/g, "/").split("/").pop() || job.job_id;
}

function explainHealth(
  verdict: FactoryVerdict,
  headline: string,
  tally: JobTally,
  attention: AttentionItem[],
): BriefingSection {
  if (attention.length > 0) {
    const extra =
      verdict === "degraded"
        ? " Failures are also showing up across shows, not only this one."
        : headline.toLowerCase().includes("this dump is failing")
          ? " Other shows look fine."
          : "";
    return {
      id: "health",
      title: "House health",
      meaning: "This show needs you.",
      detail: `${attention.length} step${attention.length === 1 ? "" : "s"} stopped. Open this heading to read why.${extra}`,
      tone: "fail",
    };
  }
  return {
    id: "health",
    title: "House health",
    meaning: "This show is clear.",
    detail:
      tally.total === 0
        ? "No jobs have run on this show yet."
        : `${tally.passed} of ${tally.total} jobs on this show have passed.`,
    tone: "ok",
  };
}

function spendLeftUndone(pulse: RunPulse, worklist?: Worklist | null): boolean {
  if (pulse.wheel.items.some((item) => item.kind === "spend")) return true;
  if ((pulse.jobs ?? []).some((job) => job.status === "throttled")) return true;
  if (worklist?.status === "waiting_for_budget") return true;
  return buildSuggestionPlan(worklist ?? null).ranked.some((row) => row.fit === "below_cutoff");
}

function explainSpend(pulse: RunPulse, worklist?: Worklist | null): BriefingSection {
  const leftover = spendLeftUndone(pulse, worklist);
  const top = pulse.burn.top[0];
  if (!top) {
    return {
      id: "spend",
      title: "Spend",
      meaning: leftover
        ? "Planned finishing work was left undone because it no longer fit the budget."
        : "Jobs did not stop because the budget ran out.",
      detail: leftover
        ? "The supervisor ranked leftover work and some of it never ran."
        : "Nothing on this show has billed yet.",
      tone: leftover ? "fail" : "ok",
    };
  }
  const stage = stationName(top.station);
  const extras = pulse.burn.top
    .slice(1)
    .map((row) => `${stationName(row.station)} ${cost(row.cost_micros)}`)
    .join("; ");
  const billed = extras
    ? `${stage} is the expensive step (${cost(top.cost_micros)}): ${top.why}. Also billed: ${extras}.`
    : `${stage} is the expensive step (${cost(top.cost_micros)}): ${top.why}.`;
  return {
    id: "spend",
    title: "Spend",
    meaning: leftover
      ? "Planned finishing work was left undone because it no longer fit the budget."
      : "Jobs did not stop because the budget ran out.",
    detail: billed,
    tone: leftover ? "fail" : "ok",
  };
}

function explainTime(pulse: RunPulse, tally: JobTally): BriefingSection {
  if (pulse.eta.remaining_items === 0) {
    return {
      id: "time",
      title: "Time left",
      meaning: "No finishing work is waiting.",
      detail: "The run can be reviewed as-is.",
      tone: "ok",
    };
  }
  const stalled = tally.working === 0;
  const waiting = `${pulse.eta.remaining_items} item${pulse.eta.remaining_items === 1 ? "" : "s"} still in the work plan.`;
  if (pulse.eta.eta_seconds == null) {
    return {
      id: "time",
      title: "Time left",
      meaning: stalled
        ? "Finishing work is still sitting in the plan."
        : "Finishing work is still moving.",
      detail: `${waiting} Typical duration for those stages is not available yet.`,
      tone: stalled ? "fail" : "ok",
    };
  }
  return {
    id: "time",
    title: "Time left",
    meaning: stalled
      ? "Finishing work is still sitting in the plan."
      : "Finishing work is still moving.",
    detail: pulse.eta.headline.replace("dump", "show"),
    tone: stalled ? "fail" : "ok",
  };
}

const STOP_KINDS = new Set(["spend", "human", "intervention"]);

function explainActions(pulse: RunPulse): BriefingSection {
  const stops = pulse.wheel.items.filter((item) => STOP_KINDS.has(item.kind));
  if (stops.length > 0) {
    const lead = explainWheelItem(stops[0]!);
    return {
      id: "actions",
      title: "What already ran on its own",
      meaning: "The house stopped work on its own.",
      detail: `${lead.text} Open this heading to read each stop.`,
      tone: "fail",
    };
  }
  const count = pulse.wheel.items.length;
  return {
    id: "actions",
    title: "What already ran on its own",
    meaning: "Nothing needed an automatic stop.",
    detail:
      count > 0
        ? `${count} note${count === 1 ? "" : "s"} recorded. Open this heading to read them.`
        : "No automatic stops, fallbacks, or supervisor looks have been recorded yet.",
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
