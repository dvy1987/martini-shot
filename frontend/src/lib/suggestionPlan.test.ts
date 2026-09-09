import { describe, expect, it } from "vitest";

import { buildSuggestionPlan } from "@/lib/suggestionPlan";
import type { InspectNote, Worklist, WorklistItem } from "@/types/api";

function note(partial: Partial<InspectNote> & Pick<InspectNote, "station">): InspectNote {
  return {
    agent: partial.agent ?? `${partial.station}-agent`,
    status: partial.status ?? "needs_work",
    impact: partial.impact ?? "medium",
    kind: partial.kind ?? "improvement",
    summary: partial.summary ?? `${partial.station} suggestion`,
    cost_estimate_micros: partial.cost_estimate_micros ?? 1_000_000,
    shot_id: partial.shot_id ?? "shot-a",
    ...partial,
  };
}

function item(partial: Partial<WorklistItem> & Pick<WorklistItem, "id" | "station">): WorklistItem {
  return {
    status: "waiting",
    summary: `${partial.station} work`,
    cost_estimate_micros: 1_000_000,
    shot_id: "shot-a",
    ...partial,
  };
}

function worklist(partial: Partial<Worklist> = {}): Worklist {
  return {
    project_id: "p1",
    budget_micros: 10_000_000,
    spent_micros: 0,
    status: "inspecting",
    attendance: [],
    items: [],
    final_refs: [],
    original_refs: [],
    ...partial,
  };
}

describe("buildSuggestionPlan", () => {
  it("stays empty until mix and pickups finish", () => {
    const plan = buildSuggestionPlan(
      worklist({
        phase: "cleanup",
        items: [
          item({ id: "loudness::shot-a", station: "loudness", status: "running" }),
          item({ id: "pickups::shot-a", station: "pickups", status: "waiting" }),
        ],
      }),
    );
    expect(plan.stage).toBe("too_early");
    expect(plan.incoming).toEqual([]);
    expect(plan.ranked).toEqual([]);
  });

  it("lists leftover station notes as they arrive, skipping empty attendance holes", () => {
    const first = buildSuggestionPlan(
      worklist({
        phase: "consulting",
        attendance: [
          note({ station: "extend", status: "needs_work", summary: "Keep rolling past the cut" }),
          note({ station: "relight", status: "empty", summary: "" }),
          note({ station: "loudness", status: "ok", summary: "Mix is in family" }),
        ],
      }),
    );
    expect(first.stage).toBe("collecting");
    expect(first.incoming.map((row) => row.station)).toEqual(["extend"]);

    const second = buildSuggestionPlan(
      worklist({
        phase: "consulting",
        attendance: [
          note({ station: "extend", status: "needs_work", summary: "Keep rolling past the cut" }),
          note({ station: "relight", status: "needs_work", summary: "Faces are underexposed" }),
          note({ station: "loudness", status: "ok", summary: "Mix is in family" }),
        ],
      }),
    );
    expect(second.incoming.map((row) => row.station)).toEqual(["extend", "relight"]);
  });

  it("stack-ranks leftover planned work and draws a budget cutoff", () => {
    const plan = buildSuggestionPlan(
      worklist({
        phase: "planning",
        status: "waiting_for_budget",
        budget_micros: 5_000_000,
        spent_micros: 0,
        items: [
          item({ id: "loudness::shot-a", station: "loudness", status: "passed", cost_estimate_micros: 80_000 }),
          item({
            id: "extend::shot-a",
            station: "extend",
            cost_estimate_micros: 3_000_000,
            summary: "Keep rolling",
          }),
          item({
            id: "relight::shot-a",
            station: "relight",
            cost_estimate_micros: 1_500_000,
            summary: "Lift faces",
          }),
          item({
            id: "coverage::shot-a",
            station: "coverage",
            cost_estimate_micros: 2_000_000,
            summary: "Add a closer angle",
          }),
        ],
      }),
    );
    expect(plan.stage).toBe("ranked");
    expect(plan.ranked.map((row) => row.item.station)).toEqual(["extend", "relight", "coverage"]);
    expect(plan.ranked.map((row) => row.rank)).toEqual([1, 2, 3]);
    expect(plan.ranked.map((row) => row.fit)).toEqual(["in_budget", "in_budget", "below_cutoff"]);
    expect(plan.cutoffAfterRank).toBe(2);
  });

  it("moves the cutoff up when a planned step costs more than its estimate", () => {
    const estimated = buildSuggestionPlan(
      worklist({
        status: "running",
        budget_micros: 5_000_000,
        spent_micros: 0,
        items: [
          item({
            id: "extend::shot-a",
            station: "extend",
            status: "running",
            cost_estimate_micros: 3_000_000,
          }),
          item({
            id: "relight::shot-a",
            station: "relight",
            cost_estimate_micros: 1_500_000,
          }),
          item({
            id: "coverage::shot-a",
            station: "coverage",
            cost_estimate_micros: 500_000,
          }),
        ],
      }),
    );
    expect(estimated.ranked.map((row) => row.fit)).toEqual(["in_budget", "in_budget", "in_budget"]);
    expect(estimated.cutoffAfterRank).toBeNull();

    const overrun = buildSuggestionPlan(
      worklist({
        status: "waiting_for_budget",
        budget_micros: 5_000_000,
        spent_micros: 4_200_000,
        items: [
          item({
            id: "extend::shot-a",
            station: "extend",
            status: "passed",
            cost_estimate_micros: 3_000_000,
            cost_actual_micros: 4_200_000,
          }),
          item({
            id: "relight::shot-a",
            station: "relight",
            cost_estimate_micros: 1_500_000,
          }),
          item({
            id: "coverage::shot-a",
            station: "coverage",
            cost_estimate_micros: 500_000,
          }),
        ],
      }),
    );
    expect(overrun.ranked.map((row) => row.fit)).toEqual(["in_budget", "below_cutoff", "below_cutoff"]);
    expect(overrun.cutoffAfterRank).toBe(1);
    expect(overrun.remainingMicros).toBe(800_000);
  });
});
