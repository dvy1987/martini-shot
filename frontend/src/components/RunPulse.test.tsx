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
  it("explains this run in English and does not send the operator to Grafana", () => {
    render(<RunPulseStrip pulse={pulse} />);
    expect(screen.getByRole("heading", { name: /^this run$/i, level: 2 })).toBeInTheDocument();
    expect(screen.getByText(/failures are showing up across shows/i)).toBeInTheDocument();
    expect(screen.getByText(/burning the budget/i)).toBeInTheDocument();
    expect(screen.getByText(/about 1 min left/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /station health/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^grafana$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /grafana watch/i })).not.toBeInTheDocument();
  });

  it("gives the four facts their own cards instead of one packed grid", () => {
    render(<RunPulseStrip pulse={pulse} />);
    const cards = screen.getAllByRole("article");
    expect(cards).toHaveLength(4);
    expect(screen.getByRole("heading", { name: /house health/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^spend$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /time left/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /what already ran/i })).toBeInTheDocument();
  });

  it("jumps to the expensive job when asked", () => {
    const onJumpToJob = vi.fn();
    render(<RunPulseStrip pulse={pulse} onJumpToJob={onJumpToJob} />);
    fireEvent.click(screen.getByRole("button", { name: /open on timeline/i }));
    expect(onJumpToJob).toHaveBeenCalledWith("job-runaway");
  });

  it("lists this run's jobs even when they cost nothing", () => {
    const onJumpToJob = vi.fn();
    render(
      <RunPulseStrip
        pulse={{
          ...pulse,
          jobs: [
            {
              job_id: "job-in-1",
              station: "ingest",
              status: "pass",
              cost_micros: 0,
              clip: "test-clip01.mp4",
            },
          ],
        }}
        onJumpToJob={onJumpToJob}
      />,
    );
    expect(screen.getByText("test-clip01.mp4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ingest · test-clip01\.mp4/i })).toBeInTheDocument();
  });

  it("says the run could not load without inventing answers", () => {
    render(
      <RunPulseStrip
        pulse={null}
        errorMessage="This run could not be loaded. Check the connection and try again."
      />,
    );
    expect(screen.getByText(/could not be loaded/i)).toBeInTheDocument();
    expect(screen.queryByText(/across shows/i)).not.toBeInTheDocument();
  });
});
