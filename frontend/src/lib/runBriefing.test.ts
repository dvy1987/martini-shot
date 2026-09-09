import { describe, expect, it } from "vitest";

import { buildRunBriefing, explainWheelItem } from "./runBriefing";
import type { RunPulse } from "@/types/api";

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
    expect(briefing.sections[0]?.meaning).toMatch(/across shows/i);
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
    expect(briefing.sections[0]?.tone).toBe("muted");
  });
});
