import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getJobClip } from "@/api/endpoints";
import TimelineBoard from "@/components/TimelineBoard";
import type { Job, Worklist } from "@/types/api";

vi.mock("@/api/endpoints", () => ({
  getJobClip: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
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
    expect(screen.getByRole("button", { name: /select clip 1 \(upload\)/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: /select clip 2 \(upload\)/i }));
    expect(onSelectJob).toHaveBeenCalledWith("job-2", expect.any(HTMLButtonElement));
    expect(screen.getAllByText("Upload").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ingest").length).toBeGreaterThan(0);
    expect(screen.queryByText(/file opens/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/spoken words/i)).not.toBeInTheDocument();
  });

  it("opens agent notes from the table instead of repeating the stage blurb", () => {
    const loud: Job = {
      ...job(3),
      job_id: "job-loud",
      station: "loudness",
      status: "pass",
      result: {
        mixed: true,
        stems: "balanced",
        agent: {
          reason:
            "Standard conversational dialogue in a stormy lighthouse interior. Current integrated loudness of -19.9 LUFS fails the streaming target.",
        },
      },
    };
    render(<TimelineBoard jobs={[loud]} selectedJobId={null} onSelectJob={vi.fn()} />);

    expect(screen.queryByText(/file opens/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/balance the mix/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /table view/i }));
    expect(screen.getByRole("columnheader", { name: /what changed/i })).toBeInTheDocument();
    expect(screen.getByText("Mixed the soundtrack")).toBeInTheDocument();
    expect(screen.queryByText(/file opens/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /agent notes for clip 1 \(fix audio\)/i }));
    expect(screen.getByRole("dialog", { name: /clip 1 · fix audio/i })).toBeInTheDocument();
    expect(screen.getByText(/stormy lighthouse/i)).toBeInTheDocument();
    expect(screen.getByText(/weather as louder than the voices/i)).toBeInTheDocument();
    expect(screen.getByText(/toward the streaming target/i)).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: /select clip 1 \(upload\)/i })).toBeInTheDocument();
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
    expect(screen.getAllByText("Clip 1").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /select clip cafe\.mp4/i })).not.toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /open clip 1 after/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /open clip 1 after/i }).querySelector("video")).toHaveAttribute(
      "preload",
      "none",
    );
    expect(getJobClip).toHaveBeenCalledWith("job-1", "before");
    expect(getJobClip).not.toHaveBeenCalledWith("job-1", "after");
    fireEvent.click(screen.getByRole("button", { name: /open clip 1 after/i }));
    expect(screen.getByRole("dialog", { name: /cafe.mp4/i })).toBeInTheDocument();
    expect(screen.getByText("After this step")).toBeInTheDocument();
    expect(screen.getByLabelText("Subtitles")).toHaveTextContent("two coffees");
    expect(screen.getByText("Scene")).toBeInTheDocument();
    expect(screen.getByText("A quiet cafe.")).toBeInTheDocument();
  });

  it("keeps Final cut empty while leftover work is still running", () => {
    const origin = "projects/project-1/ingest/job-1/cafe.mp4";
    const ingest = finishedIngest("job-1", origin, 0);
    const mixed = finishedMix("job-loud", origin);
    render(
      <TimelineBoard
        jobs={[ingest, mixed]}
        selectedJobId={null}
        onSelectJob={vi.fn()}
        worklist={runningWorklist()}
      />,
    );

    const strip = screen.getByRole("region", { name: "Final cut" });
    expect(strip).toHaveTextContent(/fills when the orchestrator has stopped/i);
    expect(screen.queryByRole("button", { name: /add to final cut/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Final Cut")).not.toBeInTheDocument();
  });

  it("groups table rows by clip journey in upload order", () => {
    const cafe = "projects/project-1/ingest/job-1/cafe.mp4";
    const street = "projects/project-1/ingest/job-2/street.mp4";
    render(
      <TimelineBoard
        jobs={[
          finishedIngest("job-2", street, 1),
          finishedMix("job-loud", cafe),
          finishedIngest("job-1", cafe, 0),
        ]}
        selectedJobId={null}
        onSelectJob={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /table view/i }));
    const table = screen.getByRole("table", { name: /season timeline jobs/i });
    const stages = [...table.querySelectorAll("[data-stage]")].map((node) =>
      node.getAttribute("data-stage"),
    );
    expect(stages).toEqual(["upload", "ingest", "loudness", "upload", "ingest"]);
    const clips = [...table.querySelectorAll("[data-clip]")].map((node) =>
      node.getAttribute("data-clip"),
    );
    expect(clips).toEqual(["Clip 1", "Clip 1", "Clip 1", "Clip 2", "Clip 2"]);
  });

  it("fills Final cut with the latest After and lets the operator swap it from the table", async () => {
    vi.mocked(getJobClip).mockImplementation(async (jobId, side) => ({
      job_id: jobId,
      side,
      clip_name: "cafe.mp4",
      url: `https://example.test/${jobId}-${side}.mp4`,
      expires_in_minutes: 15,
      metadata: {},
    }));
    const origin = "projects/project-1/ingest/job-1/cafe.mp4";
    const ingest = finishedIngest("job-1", origin, 0);
    const mixed = finishedMix("job-loud", origin);
    render(
      <TimelineBoard
        projectId="project-1"
        jobs={[ingest, mixed]}
        selectedJobId={null}
        onSelectJob={vi.fn()}
        worklist={idleWorklist()}
      />,
    );

    const strip = screen.getByRole("region", { name: "Final cut" });
    await waitFor(() =>
      expect(within(strip).getByRole("button", { name: /open cafe.mp4/i })).toBeInTheDocument(),
    );
    expect(getJobClip).toHaveBeenCalledWith("job-loud", "after");

    fireEvent.click(screen.getByRole("button", { name: /table view/i }));
    expect(screen.getByRole("columnheader", { name: /final cut/i })).toBeInTheDocument();
    expect(screen.getByText("Final Cut")).toBeInTheDocument();
    const addButtons = screen.getAllByRole("button", { name: /^add to final cut$/i });
    const addButton = addButtons[0];
    expect(addButton).toBeTruthy();
    fireEvent.click(addButton as HTMLElement);
    await waitFor(() => expect(getJobClip).toHaveBeenCalledWith("job-1", "before"));
    expect(within(strip).getByRole("button", { name: /open cafe.mp4/i })).toBeInTheDocument();
  });

  it("places a Play control next to the Final cut thumbs and plays downloaded clips in order", async () => {
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    let created = 0;
    const createUrl = vi.fn(() => `blob:final-${created++}`);
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => ({
        ok: true,
        blob: async () => new Blob([url], { type: "video/mp4" }),
      })),
    );
    vi.mocked(getJobClip).mockImplementation(async (jobId, side) => ({
      job_id: jobId,
      side,
      clip_name: `${jobId}.mp4`,
      url: `/api/v1/jobs/${jobId}/clip/${side}/media`,
      expires_in_minutes: 15,
      metadata: {},
    }));
    const firstOrigin = "projects/project-1/ingest/job-1/cafe.mp4";
    const secondOrigin = "projects/project-1/ingest/job-2/street.mp4";
    render(
      <TimelineBoard
        projectId="project-1"
        jobs={[
          finishedIngest("job-1", firstOrigin, 0),
          finishedMix("job-loud", firstOrigin),
          finishedIngest("job-2", secondOrigin, 1),
        ]}
        selectedJobId={null}
        onSelectJob={vi.fn()}
        worklist={idleWorklist()}
      />,
    );

    const strip = screen.getByRole("region", { name: "Final cut" });
    const play = within(strip).getByRole("button", { name: /^play$/i });
    expect(play.compareDocumentPosition(within(strip).getByText(/clip 1/i))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );

    fireEvent.click(play);
    expect(await screen.findByText(/downloading/i)).toBeInTheDocument();
    const player = await screen.findByRole("video", { name: /final cut playback/i });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(getJobClip).toHaveBeenCalledWith("job-loud", "after");
    expect(getJobClip).toHaveBeenCalledWith("job-2", "after");
    expect(player).toHaveAttribute("src", "blob:final-0");

    fireEvent.ended(player);
    await waitFor(() =>
      expect(screen.getByRole("video", { name: /final cut playback/i })).toHaveAttribute(
        "src",
        "blob:final-1",
      ),
    );
  });
});

function finishedIngest(jobId: string, origin: string, index: number): Job {
  return {
    job_id: jobId,
    station: "ingest",
    project_id: "project-1",
    input_refs: [origin],
    status: "pass",
    attempts: 1,
    result: { upload_index: index, ingested: true, scene: "Cafe.", probe: { duration_s: 4 } },
  };
}

function finishedMix(jobId: string, origin: string): Job {
  return {
    job_id: jobId,
    station: "loudness",
    project_id: "project-1",
    input_refs: [origin],
    status: "pass",
    attempts: 1,
    result: { artifact_ref: `${origin}-loud.mp4` },
  };
}

function idleWorklist(): Worklist {
  return {
    project_id: "project-1",
    budget_micros: 1,
    spent_micros: 0,
    status: "idle",
    attendance: [],
    items: [],
    final_refs: [],
    original_refs: [],
  };
}

function runningWorklist(): Worklist {
  return {
    ...idleWorklist(),
    status: "running",
    phase: "executing",
    items: [{ id: "extend::a", station: "extend", status: "running" }],
  };
}