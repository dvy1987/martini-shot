import { describe, expect, it } from "vitest";
import { deriveJourney } from "./journey";
import type { Job } from "@/types/api";

const job = (station: string, status: Job["status"]): Job => ({
  job_id: `${station}-${status}`, station, status, project_id: "p", input_refs: [], attempts: 1,
});

describe("deriveJourney", () => {
  it("teaches the preparation state without inventing progress", () => {
    expect(deriveJourney([], null).phase).toBe("prepare");
    expect(deriveJourney([], null).total).toBe(0);
  });
  it("follows the mandatory ingest, mix, pickup order", () => {
    expect(deriveJourney([job("ingest", "running")], null).phase).toBe("ingesting");
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
});