import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RunPulseStrip from "@/components/RunPulse";
import type { RunPulse } from "@/types/api";

afterEach(cleanup);

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
  dashboards: [
    { title: "Station Health", url: "https://chipperm.grafana.net/d/pc-station-health" },
  ],
};

describe("RunPulseStrip", () => {
  it("renders the four finishing-run questions in English", () => {
    render(<RunPulseStrip pulse={pulse} />);
    expect(screen.getByText(/factory is sick/i)).toBeInTheDocument();
    expect(screen.getByText(/omni refused/i)).toBeInTheDocument();
    expect(screen.getByText(/about 1 min left/i)).toBeInTheDocument();
    expect(screen.getByText(/spend throttle/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /station health/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /grafana watch/i })).toBeInTheDocument();
  });

  it("jumps to the expensive job when asked", () => {
    const onJumpToJob = vi.fn();
    render(<RunPulseStrip pulse={pulse} onJumpToJob={onJumpToJob} />);
    fireEvent.click(screen.getByRole("button", { name: "job-ext-9" }));
    expect(onJumpToJob).toHaveBeenCalledWith("job-ext-9");
  });

  it("says Grafana is unreachable without inventing answers", () => {
    render(
      <RunPulseStrip
        pulse={null}
        errorMessage="Run pulse could not reach Grafana."
      />,
    );
    expect(screen.getByText(/could not reach grafana/i)).toBeInTheDocument();
    expect(screen.queryByText(/factory is sick/i)).not.toBeInTheDocument();
  });
});
