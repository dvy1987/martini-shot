import { describe, expect, it } from "vitest";

import { composeAgentNotes, readAgentNotes } from "./agentNotes";
import type { Job } from "@/types/api";

function job(partial: Partial<Job> & Pick<Job, "station" | "status">): Job {
  return {
    job_id: partial.job_id ?? "job-1",
    project_id: "p1",
    input_refs: ["projects/p1/a.mp4"],
    attempts: 1,
    ...partial,
  };
}

describe("readAgentNotes", () => {
  it("does not treat a balanced mix as the storm-over-voices problem", () => {
    const notes = readAgentNotes(
      job({
        station: "loudness",
        status: "pass",
        result: {
          mixed: true,
          stems: "balanced",
          verdict: "pass",
          agent: {
            reason:
              "Standard conversational dialogue in a stormy lighthouse interior. Current integrated loudness of -19.9 LUFS fails the streaming target.",
          },
        },
      }),
    );
    expect(notes.changed).toMatch(/mixed/i);
    expect(notes.problem).toMatch(/stormy lighthouse/i);
    expect(notes.ignored).toMatch(/weather as louder than the voices/i);
    expect(notes.fixed).toMatch(/streaming/i);
    expect(notes.failed).toBe("");
  });

  it("says pickups left flicker alone when the number stayed under the limit", () => {
    const notes = readAgentNotes(
      job({
        station: "pickups",
        status: "pass",
        result: {
          repaired: false,
          flicker: { ok: true, flicker_score: 0.005 },
          agent: { reason: "Measured flicker is well below the threshold." },
        },
      }),
    );
    expect(notes.changed).toMatch(/left the picture/i);
    expect(notes.ignored).toMatch(/flicker/i);
    expect(notes.fixed).toMatch(/no repair/i);
  });

  it("explains a lighting failure in seconds, not an API code", () => {
    const notes = readAgentNotes(
      job({
        station: "relight",
        status: "fail",
        error: {
          code: "job_failed",
          message:
            "Error code: 400 - {'error': {'message': 'Editing duration 14 exceeds maximum duration 10.'}}",
        },
        result: {
          preset: "practical_lamp",
          agent: { reason: "Faces are lost in deep shadows." },
        },
      }),
    );
    expect(notes.changed).toMatch(/could not finish/i);
    expect(notes.problem).toMatch(/shadows/i);
    expect(notes.failed).toMatch(/14 seconds/i);
    expect(notes.failed).toMatch(/10 seconds/i);
    expect(notes.failed).not.toMatch(/error code/i);
  });

  it("explains a delivery frame-rate bounce without the rule id", () => {
    const notes = readAgentNotes(
      job({
        station: "delivery",
        status: "needs_human",
        error: { code: "job_failed", message: "delivery_fail" },
        result: {
          delivery: {
            verdict: "fail",
            violations: [{ message: "fps 30.273897743450156 outside profile range", rule_id: "DEL-004" }],
          },
        },
      }),
    );
    expect(notes.changed).toMatch(/did not pass/i);
    expect(notes.failed).toMatch(/frame rate/i);
    expect(notes.failed).not.toMatch(/DEL-004/);
  });

  it("writes a flowing note that covers the four facts without repeating the questions", () => {
    const notes = readAgentNotes(
      job({
        station: "loudness",
        status: "pass",
        result: {
          mixed: true,
          stems: "balanced",
          verdict: "pass",
          agent: {
            reason:
              "What they thought the problem was: the clip sat too quiet in a stormy lighthouse.",
          },
        },
      }),
    );
    const body = composeAgentNotes(notes);
    expect(body).toMatch(/stormy lighthouse/i);
    expect(body).toMatch(/weather as louder than the voices/i);
    expect(body).toMatch(/streaming/i);
    expect(body).toMatch(/did not fail/i);
    expect(body).not.toMatch(/what they thought the problem was/i);
    expect(body).not.toMatch(/what they ignored/i);
    expect(body).not.toMatch(/what they fixed/i);
    expect(body).not.toMatch(/where they failed/i);
  });
});
