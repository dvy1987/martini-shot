import { describe, expect, it } from "vitest";

import type { Deliberation, SseEvent } from "@/types/api";
import { deliberationFromSseEvent, dissentForJob, upsertDeliberation } from "@/lib/deliberations";

function deliberation(cycleId: string, jobId: string, createdAt: string): Deliberation {
  return {
    cycle_id: cycleId,
    case_id: `case-${cycleId}`,
    created_at: createdAt,
    trigger: { kind: "job_failed", job_id: jobId, project_id: "project-1" },
    specialists: ["reliability_investigator"],
    verdict: { rejected: [], approved_specialists: ["reliability_investigator"] },
    recommendation: { ranked_actions: [], dissent: [] },
    status: "proposed",
  };
}

describe("upsertDeliberation", () => {
  it("replaces by cycle_id and appends new records without mutation", () => {
    const first = deliberation("cyc-a", "job-1", "2026-09-04T00:00:00Z");
    const second = deliberation("cyc-b", "job-1", "2026-09-04T00:01:00Z");
    const rows = [first];

    const updated = deliberation("cyc-a", "job-1", "2026-09-04T00:02:00Z");
    expect(upsertDeliberation(rows, updated)).toEqual([updated]);
    expect(upsertDeliberation(rows, second)).toEqual([first, second]);
    expect(rows).toEqual([first]);
  });

  it("returns a single-entry array when the cache is empty", () => {
    const record = deliberation("cyc-a", "job-1", "2026-09-04T00:00:00Z");
    expect(upsertDeliberation([], record)).toEqual([record]);
  });
});

describe("dissentForJob", () => {
  it("returns dissent lines from the newest deliberation for the job", () => {
    const older = {
      ...deliberation("cyc-a", "job-1", "2026-09-04T00:00:00Z"),
      recommendation: { ranked_actions: [], dissent: ["stale dissent"] },
    };
    const newer = {
      ...deliberation("cyc-b", "job-1", "2026-09-04T00:05:00Z"),
      recommendation: { ranked_actions: [], dissent: ["QC and reliability disagree on retry"] },
    };
    const otherJob = deliberation("cyc-c", "job-2", "2026-09-04T00:06:00Z");

    expect(dissentForJob([older, otherJob, newer], "job-1")).toEqual([
      "QC and reliability disagree on retry",
    ]);
  });

  it("returns an empty array when there is no dissent or no deliberation", () => {
    const record = deliberation("cyc-a", "job-1", "2026-09-04T00:00:00Z");
    expect(dissentForJob([record], "job-1")).toEqual([]);
    expect(dissentForJob([record], "job-missing")).toEqual([]);
    expect(dissentForJob([], "job-1")).toEqual([]);
  });
});

describe("deliberationFromSseEvent", () => {
  it("extracts a valid deliberation.completed payload", () => {
    const record = deliberation("cyc-a", "job-1", "2026-09-04T00:00:00Z");
    const event: SseEvent = { type: "deliberation.completed", payload: record, at: record.created_at };
    expect(deliberationFromSseEvent(event)).toEqual(record);
  });

  it("rejects other event types and malformed payloads", () => {
    const event: SseEvent = { type: "job.updated", payload: {}, at: "2026-09-04T00:00:00Z" };
    expect(deliberationFromSseEvent(event)).toBeNull();
    expect(
      deliberationFromSseEvent({
        type: "deliberation.completed",
        payload: { cycle_id: "incomplete" },
        at: "2026-09-04T00:00:00Z",
      }),
    ).toBeNull();
  });
});
