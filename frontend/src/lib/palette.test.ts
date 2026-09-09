import { describe, expect, it } from "vitest";

import { filterCommands, fuzzyScore, allCommands, pathForRouteCommand, type PaletteCommand } from "@/lib/palette";
import type { Job } from "@/types/api";

const COMMANDS: PaletteCommand[] = [
  { id: "route:timeline", label: "Central station", hint: "Season board", kind: "route" },
  { id: "route:decisions", label: "Decisions", hint: "Screening room", kind: "route" },
  { id: "job:job-12f1", label: "job-12f1", hint: "ingest", kind: "job" },
  { id: "lens", label: "Toggle Lens", hint: "Reveal collapsed lanes", kind: "lens" },
];

describe("command palette matching", () => {
  it("scores substring hits above subsequence hits", () => {
    expect(fuzzyScore("job", "job-12f1")).toBe(2);
    expect(fuzzyScore("j12", "job-12f1")).toBe(1);
    expect(fuzzyScore("zzz", "job-12f1")).toBe(0);
    expect(fuzzyScore("", "anything")).toBe(1);
  });

  it("filters and ranks commands without fabricating entries", () => {
    expect(filterCommands(COMMANDS, "zzz")).toEqual([]);
    expect(filterCommands(COMMANDS, "screen").map(({ id }) => id)).toEqual(["route:decisions"]);
    expect(filterCommands(COMMANDS, "job").map(({ id }) => id)).toEqual(["job:job-12f1"]);
  });

  it("builds jump targets from observed jobs only", () => {
    const jobs: Job[] = [
      {
        job_id: "job-real",
        station: "ingest",
        project_id: "p1",
        input_refs: [],
        status: "running",
        attempts: 1,
      },
    ];
    const ids = allCommands(jobs).map(({ id }) => id);
    expect(ids).toContain("job:job-real");
    expect(ids).toContain("route:timeline");
    expect(ids).toContain("route:suggestions");
    expect(ids).toContain("route:decisions");
    expect(ids).toContain("route:analytics");
    // Unfinished screens are hidden from navigation (demo ruling).
    expect(ids).not.toContain("route:changes");
    expect(ids).not.toContain("route:reports");
    expect(ids).toContain("lens");
    expect(ids.some((id) => id.startsWith("job:") && id !== "job:job-real")).toBe(false);
  });

  it("maps route commands onto real app paths", () => {
    expect(pathForRouteCommand("route:timeline")).toBe("/");
    expect(pathForRouteCommand("route:suggestions")).toBe("/suggestions");
    expect(pathForRouteCommand("route:decisions")).toBe("/decisions");
    expect(pathForRouteCommand("route:analytics")).toBe("/analytics");
    expect(pathForRouteCommand("route:missing")).toBe("/");
  });
});
