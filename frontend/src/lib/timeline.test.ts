import { describe, expect, it } from "vitest";

import type { Job, SseEvent } from "@/types/api";
import { groupJobsByStation, jobFromSseEvent, jobsForProject, upsertJob } from "@/lib/timeline";

function job(jobId: string, station: string, status: Job["status"]): Job {
  return {
    job_id: jobId,
    station,
    project_id: "project-1",
    input_refs: [],
    status,
    attempts: 1,
  };
}

describe("groupJobsByStation", () => {
  it("groups lanes alphabetically and surfaces exceptional statuses first", () => {
    const jobs = [
      job("loudness-pass", "loudness", "pass"),
      job("ingest-failed", "ingest", "fail"),
      job("ingest-running", "ingest", "running"),
      job("ingest-queued", "ingest", "queued"),
      job("loudness-flagged", "loudness", "needs_human"),
    ];

    expect(groupJobsByStation(jobs)).toEqual([
      {
        station: "ingest",
        jobs: [
          jobs[2],
          jobs[1],
          jobs[3],
        ],
      },
      {
        station: "loudness",
        jobs: [jobs[4], jobs[0]],
      },
    ]);
  });

  it("uses job id as a deterministic tie-breaker without mutating input", () => {
    const jobs = [
      job("zeta", "dub", "running"),
      job("alpha", "dub", "running"),
      job("beta", "dub", "running"),
    ];

    expect(groupJobsByStation(jobs)[0]?.jobs.map(({ job_id }) => job_id)).toEqual([
      "alpha",
      "beta",
      "zeta",
    ]);
    expect(jobs.map(({ job_id }) => job_id)).toEqual(["zeta", "alpha", "beta"]);
  });

  it("returns no lanes for an empty project", () => {
    expect(groupJobsByStation([])).toEqual([]);
  });

  it("replaces an updated job and appends a new job without mutation", () => {
    const existing = job("job-1", "ingest", "running");
    const jobs = [existing];
    const updated = job("job-1", "ingest", "pass");
    const added = job("job-2", "loudness", "queued");

    expect(upsertJob(jobs, updated)).toEqual([updated]);
    expect(upsertJob(jobs, added)).toEqual([existing, added]);
    expect(jobs).toEqual([existing]);
  });

  it("keeps only jobs that belong to the open project", () => {
    const current = job("job-1", "ingest", "pass");
    const other: Job = { ...job("job-other", "loudness", "pass"), project_id: "other-project" };

    expect(jobsForProject([current, other], "project-1")).toEqual([current]);
    expect(jobsForProject([current, other], null)).toEqual([]);
  });

  it("extracts only valid job.updated events", () => {
    const updated = job("job-1", "ingest", "pass");
    const event: SseEvent = {
      type: "job.updated",
      payload: { job: updated },
      at: "2026-08-28T00:00:00Z",
    };

    expect(jobFromSseEvent(event)).toEqual(updated);
    expect(
      jobFromSseEvent({
        type: "annotation.created",
        payload: { annotation_id: "annotation-1" },
        at: event.at,
      }),
    ).toBeNull();
    expect(
      jobFromSseEvent({
        type: "job.updated",
        payload: { job: { job_id: "incomplete" } },
        at: event.at,
      }),
    ).toBeNull();
  });
});