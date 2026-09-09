import { describe, expect, it } from "vitest";
import { deriveJourney, PROGRESS_STAGES } from "./journey";
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