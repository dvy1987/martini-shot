import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getJobClip } from "@/api/endpoints";
import TimelineBoard from "@/components/TimelineBoard";
import type { Job } from "@/types/api";

vi.mock("@/api/endpoints", () => ({
  getJobClip: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

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

    expect(screen.queryByRole("button", { name: /in progress: job-9/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show 1 more job in upload/i }));
    expect(screen.getByRole("button", { name: /in progress: job-9/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /collapse upload lane/i }));
    expect(screen.queryByRole("button", { name: /in progress: job-9/i })).not.toBeInTheDocument();
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

    expect(screen.getByRole("button", { name: /in progress: job-9/i })).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: /select clip job-1 \(upload\)/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: /select clip job-2 \(upload\)/i }));
    expect(onSelectJob).toHaveBeenCalledWith("job-2", expect.any(HTMLButtonElement));
    expect(screen.getAllByText("Upload").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ingest").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/file opens/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/spoken words/i).length).toBeGreaterThan(0);
  });

  it("hides jobs from other projects in timeline and table views", () => {
    const foreign: Job = {
      ...job(9),
      job_id: "job-foreign",
      project_id: "other-project",
      status: "pass",
    };
    render(
      <TimelineBoard
        projectId="project-1"
        jobs={[job(1), foreign]}
        selectedJobId={null}
        onSelectJob={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /in progress: job-1/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /complete: job-foreign/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /table view/i }));
    expect(screen.getByRole("button", { name: /select clip job-1 \(upload\)/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /select clip job-foreign \(upload\)/i })).not.toBeInTheDocument();
  });

  it("names the clip and shows before/after in the table", async () => {
    vi.mocked(getJobClip).mockImplementation(async (jobId, side) => ({
      job_id: jobId,
      side,
      clip_name: "cafe.mp4",
      url: "https://example.test/cafe.mp4",
      expires_in_minutes: 15,
      metadata: { duration_s: 4, spoken_words: "two coffees", scene: "A quiet cafe." },
    }));
    const withClip: Job = {
      ...job(1),
      input_refs: ["projects/project-1/ingest/job-1/cafe.mp4"],
      status: "pass",
      result: { probe: { duration_s: 4 } },
    };
    const unchanged: Job = {
      ...job(2),
      station: "loudness",
      input_refs: ["projects/project-1/ingest/job-2/cafe.mp4"],
      status: "pass",
      result: {},
    };
    render(
      <TimelineBoard jobs={[withClip, unchanged]} selectedJobId={null} onSelectJob={vi.fn()} />,
    );

    expect(screen.getByRole("heading", { name: "Upload" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ingest" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /complete: cafe.mp4 · upload/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /complete: job-1/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /table view/i }));
    expect(screen.getByRole("columnheader", { name: /^clip$/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /^before$/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /^after$/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/no clip before this step/i)).toBeInTheDocument();
    expect(screen.getByText("No change")).toBeInTheDocument();
    expect(screen.getAllByText("Still working").length).toBeGreaterThan(0);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /open cafe.mp4 after/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /open cafe.mp4 after/i }).querySelector("video")).toHaveAttribute(
      "preload",
      "none",
    );
    expect(getJobClip).toHaveBeenCalledWith("job-1", "before");
    expect(getJobClip).not.toHaveBeenCalledWith("job-1", "after");
    fireEvent.click(screen.getByRole("button", { name: /open cafe.mp4 after/i }));
    expect(screen.getByRole("dialog", { name: /cafe.mp4/i })).toBeInTheDocument();
    expect(screen.getByText("After this step")).toBeInTheDocument();
    expect(screen.getByLabelText("Subtitles")).toHaveTextContent("two coffees");
    expect(screen.getByText("Scene")).toBeInTheDocument();
    expect(screen.getByText("A quiet cafe.")).toBeInTheDocument();
  });
});