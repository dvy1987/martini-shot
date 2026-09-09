import { describe, expect, it } from "vitest";
import { deriveJourney, progressStageTone, PROGRESS_STAGES } from "./journey";
import type { Job, Worklist } from "@/types/api";

const job = (station: string, status: Job["status"]): Job => ({
  job_id: `${station}-${status}`, station, status, project_id: "p", input_refs: [], attempts: 1,
});

describe("deriveJourney", () => {
  it("teaches the preparation state without inventing progress", () => {
    expect(deriveJourney([], null).phase).toBe("prepare");
    expect(deriveJourney([], null).total).toBe(0);
  });
  it("follows upload, ingest watch, mix, then pickups", () => {
    expect(deriveJourney([job("ingest", "running")], null).phase).toBe("uploading");
    expect(deriveJourney([job("ingest", "pass")], null).phase).toBe("uploaded");
    const watching = {
      project_id: "p",
      budget_micros: 1,
      spent_micros: 0,
      status: "inspecting",
      attendance: [],
      items: [],
      final_refs: [],
      original_refs: [],
    };
    expect(deriveJourney([job("ingest", "pass")], watching).phase).toBe("watching");
    expect(deriveJourney([job("ingest", "pass"), job("loudness", "running")], null).phase).toBe("mixing");
    expect(deriveJourney([job("ingest", "pass"), job("loudness", "pass"), job("pickups", "running")], null).phase).toBe("repairing");
  });
  it("prioritizes a genuine fault", () => {
    expect(deriveJourney([job("ingest", "quarantined")], null).phase).toBe("attention");
  });
  it("still counts passed leftover jobs when only some have failed", () => {
    const leftover: Worklist = {
      project_id: "p",
      budget_micros: 1,
      spent_micros: 0,
      status: "running",
      phase: "executing",
      attendance: [],
      items: [
        ...Array.from({ length: 9 }, (_, index) => ({
          id: `ok-${index}`,
          station: "extend",
          status: "passed",
        })),
        { id: "bad-1", station: "corrections", status: "failed" },
        { id: "bad-2", station: "relight", status: "failed" },
      ],
      final_refs: [],
      original_refs: [],
    };
    const summary = deriveJourney(
      [job("ingest", "pass"), job("loudness", "pass"), job("pickups", "pass")],
      leftover,
    );
    expect(summary.phase).toBe("attention");
    expect(summary.completed).toBe(9);
    expect(summary.total).toBe(11);
    expect(summary.attention).toBe(2);
  });
  it("keeps consultation and planning distinct from execution", () => {
    const inspecting = { project_id: "p", budget_micros: 1, spent_micros: 0, status: "inspecting", attendance: [], items: [], final_refs: [], original_refs: [] };
    expect(deriveJourney([job("ingest", "pass"), job("loudness", "pass"), job("pickups", "pass")], inspecting).phase).toBe("consulting");
    const planning = { ...inspecting, status: "ranking" };
    expect(deriveJourney([job("ingest", "pass"), job("loudness", "pass"), job("pickups", "pass")], planning).phase).toBe("planning");
  });
  it("names Plan work, Execute, then Delivery as the last house stage", () => {
    expect(PROGRESS_STAGES.map((stage) => stage.name)).toEqual([
      "Upload",
      "Ingest",
      "Fix audio",
      "Pickups",
      "Review clips",
      "Plan work",
      "Execute",
      "Delivery",
    ]);
    expect(PROGRESS_STAGES.at(-1)?.phase).toBe("delivering");
  });
  it("runs leftover work before Delivery, and stays on Delivery until that check finishes", () => {
    const leftover: Worklist = {
      project_id: "p",
      budget_micros: 1,
      spent_micros: 0,
      status: "running",
      phase: "executing",
      attendance: [],
      items: [
        { id: "extend::s", station: "extend", status: "running" },
        { id: "delivery::s", station: "delivery", status: "waiting" },
      ],
      final_refs: [],
      original_refs: [],
    };
    const done = [job("ingest", "pass"), job("loudness", "pass"), job("pickups", "pass")];
    expect(deriveJourney(done, leftover).phase).toBe("executing");
    const first = leftover.items[0];
    if (!first) throw new Error("expected leftover extend row");
    leftover.items[0] = { ...first, status: "passed" };
    expect(deriveJourney(done, leftover).phase).toBe("delivering");
    const delivery = leftover.items[1];
    if (!delivery) throw new Error("expected leftover delivery row");
    leftover.items[1] = { ...delivery, status: "passed" };
    expect(deriveJourney(done, leftover).phase).toBe("complete");
  });
  it("does not keep ingest in progress after mix has already been queued", () => {
    const cleanup = {
      project_id: "p",
      budget_micros: 1,
      spent_micros: 0,
      status: "inspecting",
      phase: "cleanup",
      attendance: [],
      items: [
        { id: "loudness::s", station: "loudness", status: "passed" },
        { id: "pickups::s", station: "pickups", status: "passed" },
      ],
      final_refs: [],
      original_refs: [],
    };
    expect(deriveJourney([job("ingest", "pass")], cleanup).phase).not.toBe("watching");
  });
});

describe("progressStageTone", () => {
  it("marks earlier stages complete, the current stage in progress, and later stages pending", () => {
    expect(progressStageTone("uploading", "mixing")).toBe("complete");
    expect(progressStageTone("watching", "mixing")).toBe("complete");
    expect(progressStageTone("mixing", "mixing")).toBe("active");
    expect(progressStageTone("repairing", "mixing")).toBe("pending");
  });

  it("keeps finished stages complete when a later stage failed", () => {
    const jobs = [job("ingest", "pass"), job("loudness", "fail")];
    expect(progressStageTone("uploading", "attention", jobs)).toBe("complete");
    expect(progressStageTone("watching", "attention", jobs)).toBe("complete");
    expect(progressStageTone("mixing", "attention", jobs)).toBe("failed");
    expect(progressStageTone("repairing", "attention", jobs)).toBe("pending");
  });

  it("paints every stage complete after the run finishes", () => {
    expect(progressStageTone("delivering", "complete")).toBe("complete");
    expect(progressStageTone("uploading", "complete")).toBe("complete");
  });
});