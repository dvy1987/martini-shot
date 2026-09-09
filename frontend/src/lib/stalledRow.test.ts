import { describe, expect, it } from "vitest";

import { canAcceptRow, canRetryRow, worklistItemForJob } from "@/lib/stalledRow";
import type { Job, Worklist } from "@/types/api";

function job(jobId: string): Job {
  return {
    job_id: jobId,
    station: "pickups",
    project_id: "p",
    input_refs: [],
    status: "needs_human",
    attempts: 1,
  };
}

function worklistWithItem(status: string, jobId = "job-1"): Worklist {
  return {
    project_id: "p",
    budget_micros: 1,
    spent_micros: 0,
    status: "running",
    attendance: [],
    items: [{ id: "pickups::shot-4", station: "pickups", status, job_id: jobId }],
    final_refs: [],
    original_refs: [],
  };
}

describe("worklistItemForJob", () => {
  it("finds the worklist item that shares this job's job_id", () => {
    const worklist = worklistWithItem("failed");
    expect(worklistItemForJob(job("job-1"), worklist)?.id).toBe("pickups::shot-4");
  });

  it("returns null when no item references this job", () => {
    expect(worklistItemForJob(job("job-9"), worklistWithItem("failed"))).toBeNull();
  });

  it("returns null without a worklist", () => {
    expect(worklistItemForJob(job("job-1"), null)).toBeNull();
  });
});

describe("canRetryRow", () => {
  it.each(["failed", "paused", "needs_human"])("is retryable when the item is %s", (status) => {
    expect(canRetryRow(job("job-1"), worklistWithItem(status))).toBe(true);
  });

  it.each(["passed", "waiting", "queued", "running"])(
    "is not retryable when the item is %s",
    (status) => {
      expect(canRetryRow(job("job-1"), worklistWithItem(status))).toBe(false);
    },
  );

  it("is not retryable when no worklist item matches", () => {
    expect(canRetryRow(job("job-9"), worklistWithItem("failed"))).toBe(false);
  });
});

describe("canAcceptRow", () => {
  it.each(["failed", "needs_human"])("is acceptable when the item is %s", (status) => {
    expect(canAcceptRow(job("job-1"), worklistWithItem(status))).toBe(true);
  });

  it("refuses a budget pause — that is a spend throttle, not a quality call", () => {
    expect(canAcceptRow(job("job-1"), worklistWithItem("paused"))).toBe(false);
  });

  it.each(["passed", "waiting", "queued", "running"])(
    "is not acceptable when the item is %s",
    (status) => {
      expect(canAcceptRow(job("job-1"), worklistWithItem(status))).toBe(false);
    },
  );

  it("is not acceptable when no worklist item matches", () => {
    expect(canAcceptRow(job("job-9"), worklistWithItem("failed"))).toBe(false);
  });
});
