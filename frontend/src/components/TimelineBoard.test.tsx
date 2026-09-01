import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TimelineBoard from "@/components/TimelineBoard";
import type { Job } from "@/types/api";

afterEach(cleanup);

function job(index: number): Job {
  return {
    job_id: `job-${index}`,
    station: "ingest",
    project_id: "project-1",
    input_refs: [],
    status: "running",
    attempts: 1,
  };
}

describe("TimelineBoard", () => {
  it("lets operators expand and collapse lanes with more than eight jobs", () => {
    render(
      <TimelineBoard
        jobs={Array.from({ length: 9 }, (_, index) => job(index + 1))}
        selectedJobId={null}
        onSelectJob={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /in the lab: job-9/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show 1 more job in ingest/i }));
    expect(screen.getByRole("button", { name: /in the lab: job-9/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /collapse ingest lane/i }));
    expect(screen.queryByRole("button", { name: /in the lab: job-9/i })).not.toBeInTheDocument();
  });

  it("Lens expands collapsed jobs and reveals the filter row", () => {
    render(
      <TimelineBoard
        jobs={Array.from({ length: 9 }, (_, index) => job(index + 1))}
        selectedJobId={null}
        onSelectJob={vi.fn()}
        lensOpen
        statusFilter={new Set()}
        onToggleStatus={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /in the lab: job-9/i })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /filter jobs by status/i })).toBeInTheDocument();
  });

  it("shows the same jobs in table view and preserves selection behavior", () => {
    const onSelectJob = vi.fn();
    render(
      <TimelineBoard
        jobs={[job(1), job(2)]}
        selectedJobId="job-1"
        onSelectJob={onSelectJob}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /table view/i }));

    expect(screen.getByRole("table", { name: /season timeline jobs/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /select job job-1/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: /select job job-2/i }));
    expect(onSelectJob).toHaveBeenCalledWith("job-2", expect.any(HTMLButtonElement));
  });
});