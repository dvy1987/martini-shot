import { describe, expect, it } from "vitest";

import { afterState, boardRows, clipName, groupBoardLanes, withWatchNotes } from "@/lib/clipDisplay";
import type { Job } from "@/types/api";

function job(partial: Partial<Job> = {}): Job {
  return {
    job_id: "job-1",
    station: "ingest",
    project_id: "p1",
    input_refs: ["projects/p1/ingest/job-1/test-clip01.mp4"],
    status: "pass",
    attempts: 1,
    ...partial,
  };
}

describe("clipDisplay", () => {
  it("names the clip from the file, not the job id", () => {
    expect(clipName(job())).toBe("test-clip01.mp4");
  });

  it("treats a file check with probe data as an after clip", () => {
    expect(
      afterState(
        job({
          result: { probe: { duration_s: 10, codec: "h264" } },
        }),
      ),
    ).toBe("clip");
  });

  it("says no change when the step did not write a new clip or metadata", () => {
    expect(afterState(job({ result: {} }))).toBe("no_change");
    expect(afterState(job({ status: "running", result: {} }))).toBe("pending");
  });

  it("splits an ingest job into upload then ingest board rows", () => {
    const rows = boardRows([
      job({ result: { probe: { duration_s: 10 } } }),
    ]);
    expect(rows.map((row) => row.displayStation)).toEqual(["upload", "ingest"]);
    expect(rows[0]?.before).toBe("none");
    expect(rows[0]?.after).toBe("clip");
    expect(rows[0]?.afterSide).toBe("before");
    expect(rows[1]?.before).toBe("clip");
    expect(rows[1]?.after).toBe("pending");
    expect(rows[1]?.displayStatus).toBe("running");
  });

  it("shows ingest after the watch notes land", () => {
    const rows = boardRows([
      job({
        result: { ingested: true, spoken_words: "", scene: "A quiet cafe." },
      }),
    ]);
    expect(rows[1]?.after).toBe("clip");
    expect(rows[1]?.displayStatus).toBe("pass");
  });

  it("completes ingest when a later stage already carries the watch notes", () => {
    const ingest = job({ result: { probe: { duration_s: 10 } } });
    const mixed = job({
      job_id: "loud-1",
      station: "loudness",
      status: "pass",
      input_refs: ingest.input_refs,
      result: { ingested: true, spoken_words: "", scene: "A quiet cafe." },
    });
    const rows = boardRows([ingest, mixed]);
    const watch = rows.find((row) => row.displayStation === "ingest");
    expect(watch?.displayStatus).toBe("pass");
    expect(watch?.after).toBe("clip");
  });

  it("keeps upload ahead of ingest on the board", () => {
    const lanes = groupBoardLanes([
      job({ station: "loudness", input_refs: ["cafe.mp4"] }),
      job(),
    ]);
    expect(lanes.map((lane) => lane.station)).toEqual(["upload", "ingest", "loudness"]);
  });

  it("copies ingest scene notes onto the after clip", () => {
    const clip = {
      job_id: "job-1",
      side: "after" as const,
      clip_name: "test-clip01.mp4",
      url: "/api/v1/jobs/job-1/clip/after/media",
      expires_in_minutes: 60,
      metadata: { duration_s: 4 },
    };
    const mixed = job({
      result: { ingested: true, spoken_words: "Hello.", scene: "A quiet cafe." },
    });
    const next = withWatchNotes(clip, mixed, [mixed]);
    expect(next.metadata.scene).toBe("A quiet cafe.");
    expect(next.metadata.spoken_words).toBe("Hello.");
    expect(next.metadata.duration_s).toBe(4);
  });
});
