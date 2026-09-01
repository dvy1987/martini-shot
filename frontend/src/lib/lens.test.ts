import { describe, expect, it } from "vitest";

import { filterJobsByStatus, toggleStatus } from "@/lib/lens";
import type { Job } from "@/types/api";

function job(jobId: string, status: Job["status"]): Job {
  return {
    job_id: jobId,
    station: "ingest",
    project_id: "p1",
    input_refs: [],
    status,
    attempts: 1,
  };
}

describe("Lens filters", () => {
  it("returns the observed jobs unchanged when no status is selected", () => {
    const jobs = [job("a", "pass"), job("b", "fail")];
    expect(filterJobsByStatus(jobs, new Set())).toEqual(jobs);
  });

  it("keeps only the selected statuses", () => {
    const jobs = [job("a", "pass"), job("b", "fail"), job("c", "queued")];
    expect(filterJobsByStatus(jobs, new Set(["fail"]))).toEqual([jobs[1]]);
  });

  it("toggles a status in the filter set without mutating the original", () => {
    const start = new Set<Job["status"]>(["fail"]);
    const added = toggleStatus(start, "pass");
    expect([...added].sort()).toEqual(["fail", "pass"]);
    expect(start.has("pass")).toBe(false);
    expect(toggleStatus(added, "fail").has("fail")).toBe(false);
  });
});
