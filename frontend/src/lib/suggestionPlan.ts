/** Leftover-station suggestions and the live budget cutoff on the ranked plan. */

import type { InspectNote, Worklist, WorklistItem } from "@/types/api";

export const LEFTOVER_STATIONS = [
  "extend",
  "corrections",
  "relight",
  "coverage",
  "camera_language",
  "dub",
  "delivery",
] as const;

export type SuggestionStage = "too_early" | "collecting" | "ranked";
export type SuggestionFit = "in_budget" | "below_cutoff";

export interface RankedSuggestion {
  rank: number;
  item: WorklistItem;
  estimateMicros: number;
  actualMicros: number | null;
  billedMicros: number;
  fit: SuggestionFit;
}

export interface SuggestionPlan {
  stage: SuggestionStage;
  incoming: InspectNote[];
  ranked: RankedSuggestion[];
  cutoffAfterRank: number | null;
  remainingMicros: number;
  budgetMicros: number;
  spentMicros: number;
}

export function isLeftoverStation(station: string): boolean {
  return (LEFTOVER_STATIONS as readonly string[]).includes(station);
}

function emptyPlan(
  stage: SuggestionStage,
  extras: Partial<SuggestionPlan> = {},
): SuggestionPlan {
  return {
    stage,
    incoming: [],
    ranked: [],
    cutoffAfterRank: null,
    remainingMicros: 0,
    budgetMicros: 0,
    spentMicros: 0,
    ...extras,
  };
}

function leftoverAttendance(notes: readonly InspectNote[]): InspectNote[] {
  return notes.filter((row) => isLeftoverStation(row.station) && row.status !== "empty");
}

function leftoverItems(items: readonly WorklistItem[]): WorklistItem[] {
  return items.filter((item) => isLeftoverStation(item.station));
}

function alreadyBilled(item: WorklistItem): boolean {
  return (
    item.cost_actual_micros != null ||
    item.status === "passed" ||
    item.status === "failed"
  );
}

function estimateOf(item: WorklistItem): number {
  return item.cost_estimate_micros ?? 0;
}

function billedOf(item: WorklistItem): number {
  return item.cost_actual_micros ?? estimateOf(item);
}

function rankLeftover(items: readonly WorklistItem[], remaining: number): RankedSuggestion[] {
  let pocket = remaining;
  let crossed = false;
  return items.map((item, index) => {
    const estimateMicros = estimateOf(item);
    const actualMicros = item.cost_actual_micros ?? null;
    const billedMicros = billedOf(item);
    let fit: SuggestionFit;
    if (alreadyBilled(item)) {
      fit = "in_budget";
    } else if (crossed || billedMicros > pocket) {
      crossed = true;
      fit = "below_cutoff";
    } else {
      pocket -= billedMicros;
      fit = "in_budget";
    }
    return {
      rank: index + 1,
      item,
      estimateMicros,
      actualMicros,
      billedMicros,
      fit,
    };
  });
}

function cutoffAfterRank(ranked: readonly RankedSuggestion[]): number | null {
  if (!ranked.some((row) => row.fit === "below_cutoff")) {
    return null;
  }
  const lastFunded = [...ranked].reverse().find((row) => row.fit === "in_budget");
  return lastFunded?.rank ?? 0;
}

export function buildSuggestionPlan(worklist: Worklist | null): SuggestionPlan {
  if (!worklist) {
    return emptyPlan("too_early");
  }
  const budgetMicros = worklist.budget_micros ?? 0;
  const spentMicros = worklist.spent_micros ?? 0;
  const remainingMicros = Math.max(0, budgetMicros - spentMicros);
  const incoming = leftoverAttendance(worklist.attendance ?? []);
  const leftover = leftoverItems(worklist.items ?? []);
  const envelope = { remainingMicros, budgetMicros, spentMicros };

  if (worklist.phase === "cleanup") {
    return emptyPlan("too_early", envelope);
  }
  if (leftover.length > 0) {
    const ranked = rankLeftover(leftover, remainingMicros);
    return {
      stage: "ranked",
      incoming,
      ranked,
      cutoffAfterRank: cutoffAfterRank(ranked),
      ...envelope,
    };
  }
  if (
    incoming.length > 0 ||
    worklist.phase === "consulting" ||
    worklist.phase === "planning" ||
    worklist.status === "ranking" ||
    worklist.status === "planning"
  ) {
    return emptyPlan("collecting", { ...envelope, incoming });
  }
  return emptyPlan("too_early", envelope);
}
