import { describe, expect, it } from "vitest";

import { buildRunBriefing, explainWheelItem } from "./runBriefing";
import type { RunPulse, Worklist } from "@/types/api";

const pulse: RunPulse = {
  project_id: "p1",
  grafana: "ok",
  factory: {
    verdict: "degraded",
    headline: "The factory is sick — failures across projects, not just this dump.",
    evidence_url: "https://chipperm.grafana.net/d/pc-station-health",
  },
  burn: {
    headline: "extend on job-ext-9 is the expensive one — Omni refused; Veo finished it.",
    top: [
      {
        job_id: "job-ext-9",
        station: "extend",
        cost_micros: 4_000_000,
        why: "Omni refused; Veo finished it",
      },
    ],
    evidence_url: "https://chipperm.grafana.net/d/pc-finishing-cost",
  },
  eta: {
    headline: "About 1 min left for 2 remaining items.",
    eta_seconds: 80,
    remaining_items: 2,
  },
  wheel: {
    items: [
      {
        at: "2026-09-07T12:00:00Z",
        kind: "spend",
        text: "spend throttle job_id=job-runaway",
        job_id: "job-runaway",
      },
    ],
  },
  jobs: [
    {
      job_id: "job-in-1",
      station: "ingest",
      status: "pass",
      cost_micros: 0,
      clip: "test-clip01.mp4",
    },
  ],
};

describe("run briefing", () => {
  it("explains health, spend, time, and actions without sending the operator to Grafana", () => {
    const briefing = buildRunBriefing(pulse);
    expect(briefing.title).toBe("This run");
    expect(briefing.sourceLine).not.toMatch(/grafana/i);
    expect(briefing.sections.map((section) => section.title)).toEqual([
      "House health",
      "Spend",
      "Time left",
      "What already ran on its own",
    ]);
    expect(briefing.sections[0]?.meaning).toMatch(/this show is clear/i);
    expect(briefing.sections[1]?.detail).toMatch(/extend a shot/i);
    expect(briefing.sections[1]?.detail).toMatch(/4\.00/);
    expect(JSON.stringify(briefing)).not.toMatch(/grafana\.net/i);
  });

  it("turns a spend annotation into a budget stop the operator can read", () => {
    const action = explainWheelItem(pulse.wheel.items[0]!);
    expect(action.label).toBe("Budget stop");
    expect(action.text).toMatch(/burning the budget/i);
    expect(action.text).not.toMatch(/job_id=/);
    expect(action.jobId).toBe("job-runaway");
  });

  it("says when house health could not be confirmed without naming Grafana", () => {
    const briefing = buildRunBriefing({
      ...pulse,
      grafana: "unavailable",
      factory: { verdict: "unknown", headline: "Factory health is unknown until Grafana answers." },
    });
    expect(briefing.healthConfirmed).toBe(false);
    expect(briefing.sourceLine).toMatch(/could not be confirmed/i);
    expect(briefing.sourceLine).not.toMatch(/grafana/i);
    expect(briefing.sections[0]?.tone).toBe("ok");
  });

  it("leads with why Execute and Delivery stopped on this show", () => {
    const briefing = buildRunBriefing({
      ...pulse,
      factory: { verdict: "healthy", headline: "Factory looks healthy." },
      jobs: [
        {
          job_id: "job-relight-1",
          station: "relight",
          status: "fail",
          cost_micros: 0,
          clip: "test-clip03.mp4",
          error: {
            code: "job_failed",
            message:
              "Error code: 400 - {'error': {'message': 'Editing duration 14 exceeds maximum duration 10.'}}",
          },
          result: { agent: { reason: "Faces are lost in deep shadows." } },
        },
        {
          job_id: "job-del-1",
          station: "delivery",
          status: "needs_human",
          cost_micros: 0,
          clip: "test-clip01.mp4",
          error: { code: "job_failed", message: "delivery_fail" },
          result: {
            delivery: {
              verdict: "fail",
              violations: [
                { message: "fps 30.273897743450156 outside profile range", rule_id: "DEL-004" },
              ],
            },
          },
        },
      ],
    });
    expect(briefing.sourceLine).toMatch(/needs you/i);
    expect(briefing.sourceLine).not.toMatch(/grafana/i);
    expect(briefing.attention).toHaveLength(2);
    expect(briefing.attention[0]).toMatchObject({
      lane: "execute",
      jobId: "job-relight-1",
      clip: "test-clip03.mp4",
    });
    expect(briefing.attention[0]?.heading).toMatch(/execute/i);
    expect(briefing.attention[0]?.heading).toMatch(/lighting/i);
    expect(briefing.attention[0]?.why).toMatch(/14 seconds/i);
    expect(briefing.attention[0]?.why).not.toMatch(/error code/i);
    expect(briefing.attention[0]?.next).toMatch(/timeline/i);
    expect(briefing.attention[0]?.next).toMatch(/agent notes/i);
    expect(briefing.attention[1]).toMatchObject({
      lane: "delivery",
      jobId: "job-del-1",
      clip: "test-clip01.mp4",
    });
    expect(briefing.attention[1]?.heading).toMatch(/delivery/i);
    expect(briefing.attention[1]?.why).toMatch(/frame rate/i);
    expect(briefing.attention[1]?.why).not.toMatch(/DEL-004/);
    expect(briefing.attention[1]?.next).toMatch(/shipment/i);
  });

  it("prefers live Timeline jobs when run-pulse rows omit the error", () => {
    const briefing = buildRunBriefing(
      {
        ...pulse,
        jobs: [
          {
            job_id: "job-relight-1",
            station: "relight",
            status: "fail",
            cost_micros: 0,
            clip: "test-clip03.mp4",
          },
        ],
      },
      [
        {
          job_id: "job-relight-1",
          station: "relight",
          project_id: "p1",
          input_refs: ["gs://b/test-clip03.mp4"],
          status: "fail",
          attempts: 1,
          error: {
            code: "job_failed",
            message:
              "Error code: 400 - {'error': {'message': 'Editing duration 14 exceeds maximum duration 10.'}}",
          },
          result: { agent: { reason: "Faces are lost in deep shadows." } },
        },
      ],
    );
    expect(briefing.attention[0]?.why).toMatch(/14 seconds/i);
  });

  it("colors House health from this show's pending jobs, not a hardcoded red", () => {
    const blocked = buildRunBriefing({
      ...pulse,
      factory: { verdict: "healthy", headline: "Factory looks healthy." },
      jobs: [
        {
          job_id: "job-relight-1",
          station: "relight",
          status: "fail",
          cost_micros: 0,
          clip: "test-clip03.mp4",
        },
      ],
    });
    expect(blocked.sections.find((section) => section.id === "health")?.tone).toBe("fail");
    const clear = buildRunBriefing({
      ...pulse,
      factory: { verdict: "degraded", headline: "The factory is sick." },
      wheel: { items: [] },
      jobs: [
        {
          job_id: "job-in-1",
          station: "ingest",
          status: "pass",
          cost_micros: 0,
          clip: "test-clip01.mp4",
        },
      ],
    });
    expect(clear.sections.find((section) => section.id === "health")?.tone).toBe("ok");
  });

  it("colors Spend red only when planned work was left undone for budget", () => {
    const leftover: Worklist = {
      project_id: "p1",
      budget_micros: 1_000_000,
      spent_micros: 1_000_000,
      status: "waiting_for_budget",
      attendance: [],
      items: [
        {
          id: "wl-relight",
          station: "relight",
          status: "waiting",
          cost_estimate_micros: 5_000_000,
        },
        {
          id: "wl-extend",
          station: "extend",
          status: "passed",
          cost_actual_micros: 800_000,
        },
      ],
      final_refs: [],
      original_refs: [],
    };
    const stopped = buildRunBriefing(
      { ...pulse, wheel: { items: [] } },
      undefined,
      leftover,
    );
    expect(stopped.sections.find((section) => section.id === "spend")?.tone).toBe("fail");
    const clear = buildRunBriefing({
      ...pulse,
      wheel: { items: [] },
      jobs: [
        {
          job_id: "job-in-1",
          station: "ingest",
          status: "pass",
          cost_micros: 80_000,
          clip: "test-clip01.mp4",
        },
      ],
    });
    expect(clear.sections.find((section) => section.id === "spend")?.tone).toBe("ok");
  });

  it("colors Time left and automatic actions from leftover work and stops", () => {
    const stalled = buildRunBriefing({
      ...pulse,
      wheel: { items: [] },
      jobs: [
        {
          job_id: "job-in-1",
          station: "ingest",
          status: "pass",
          cost_micros: 0,
          clip: "test-clip01.mp4",
        },
      ],
    });
    expect(stalled.sections.find((section) => section.id === "time")?.tone).toBe("fail");
    expect(stalled.sections.find((section) => section.id === "actions")?.tone).toBe("ok");
    const moving = buildRunBriefing({
      ...pulse,
      eta: { headline: "About 1 min left for 2 remaining items.", eta_seconds: 80, remaining_items: 2 },
      wheel: {
        items: [
          {
            at: "2026-09-07T12:00:00Z",
            kind: "spend",
            text: "spend throttle job_id=job-runaway",
            job_id: "job-runaway",
          },
        ],
      },
      jobs: [
        {
          job_id: "job-relight-1",
          station: "relight",
          status: "running",
          cost_micros: 0,
          clip: "test-clip03.mp4",
        },
      ],
    });
    expect(moving.sections.find((section) => section.id === "time")?.tone).toBe("ok");
    expect(moving.sections.find((section) => section.id === "actions")?.tone).toBe("fail");
    const wrapped = buildRunBriefing({
      ...pulse,
      eta: { headline: "Nothing left in the worklist.", eta_seconds: 0, remaining_items: 0 },
      wheel: { items: [] },
      jobs: [
        {
          job_id: "job-in-1",
          station: "ingest",
          status: "pass",
          cost_micros: 0,
          clip: "test-clip01.mp4",
        },
      ],
    });
    expect(wrapped.sections.find((section) => section.id === "time")?.tone).toBe("ok");
    expect(wrapped.sections.find((section) => section.id === "actions")?.tone).toBe("ok");
  });
});
