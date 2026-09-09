import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FinishBar from "@/components/FinishBar";
import { getJob, ingestClip, startFinish } from "@/api/endpoints";
import type { Job } from "@/types/api";

vi.mock("@/api/endpoints", () => ({
  getJob: vi.fn(),
  ingestClip: vi.fn(),
  startFinish: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function job(id: string, ref: string): Job {
  return {
    job_id: id,
    station: "ingest",
    project_id: "p1",
    input_refs: [ref],
    status: "queued",
    attempts: 0,
  };
}

function passed(id: string, ref: string): Job {
  return { ...job(id, ref), status: "pass", attempts: 1 };
}

describe("FinishBar", () => {
  it("accepts chosen clips immediately in selection order", async () => {
    const first = new File(["a"], "a.mp4", { type: "video/mp4" });
    const second = new File(["b"], "b.mp4", { type: "video/mp4" });
    vi.mocked(ingestClip)
      .mockResolvedValueOnce(job("job-a", "a.mp4"))
      .mockResolvedValueOnce(job("job-b", "b.mp4"));
    vi.mocked(getJob)
      .mockResolvedValueOnce(passed("job-a", "a.mp4"))
      .mockResolvedValueOnce(passed("job-b", "b.mp4"));
    vi.mocked(startFinish).mockResolvedValue({
      project_id: "p1",
      budget_micros: 50_000_000,
      spent_micros: 0,
      status: "inspecting",
      attendance: [],
      items: [],
      final_refs: [],
      original_refs: [],
    });
    render(<FinishBar projectId="p1" />);
    fireEvent.change(screen.getByLabelText(/upload media/i), {
      target: { files: [first, second] },
    });
    await waitFor(() => expect(ingestClip).toHaveBeenNthCalledWith(1, "p1", first));
    expect(ingestClip).toHaveBeenNthCalledWith(2, "p1", second);
    expect(screen.queryByRole("button", { name: /add .* clip/i })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /call wrap/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /call wrap/i }));
    await waitFor(() => expect(startFinish).toHaveBeenCalledWith("p1", 50_000_000, ["job-a", "job-b"]));
  });

  it("lets the operator drag accepted clips into a new order before finishing", async () => {
    const first = new File(["a"], "a.mp4", { type: "video/mp4" });
    const second = new File(["b"], "b.mp4", { type: "video/mp4" });
    vi.mocked(ingestClip)
      .mockResolvedValueOnce(job("job-a", "a.mp4"))
      .mockResolvedValueOnce(job("job-b", "b.mp4"));
    vi.mocked(getJob)
      .mockResolvedValueOnce(passed("job-a", "a.mp4"))
      .mockResolvedValueOnce(passed("job-b", "b.mp4"));
    vi.mocked(startFinish).mockResolvedValue({
      project_id: "p1",
      budget_micros: 50_000_000,
      spent_micros: 0,
      status: "inspecting",
      attendance: [],
      items: [],
      final_refs: [],
      original_refs: [],
    });
    render(<FinishBar projectId="p1" />);
    fireEvent.change(screen.getByLabelText(/upload media/i), {
      target: { files: [first, second] },
    });
    await waitFor(() => expect(screen.getByText("a.mp4")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: /call wrap/i })).toBeEnabled());
    fireEvent.dragStart(screen.getByRole("listitem", { name: /clip 2: b\.mp4/i }));
    fireEvent.drop(screen.getByRole("listitem", { name: /clip 1: a\.mp4/i }));
    fireEvent.click(screen.getByRole("button", { name: /call wrap/i }));
    await waitFor(() => expect(startFinish).toHaveBeenCalledWith("p1", 50_000_000, ["job-b", "job-a"]));
  });

  it("lists and accepts mp4s even when the browser leaves the mime type blank", async () => {
    const file = new File(["x"], "take-01.mp4", { type: "" });
    vi.mocked(ingestClip).mockResolvedValue(job("job-1", "take-01.mp4"));
    vi.mocked(getJob).mockResolvedValue(passed("job-1", "take-01.mp4"));
    render(<FinishBar projectId="p1" />);
    fireEvent.change(screen.getByLabelText(/upload media/i), { target: { files: [file] } });
    expect(screen.getByText("take-01.mp4")).toBeInTheDocument();
    await waitFor(() => expect(ingestClip).toHaveBeenCalledWith("p1", file));
  });

  it("keeps uploading the rest when one clip fails", async () => {
    const first = new File(["a"], "test-clip01.mp4", { type: "video/mp4" });
    const second = new File(["b"], "test-clip02.mp4", { type: "video/mp4" });
    vi.mocked(ingestClip)
      .mockRejectedValueOnce(new Error("broken file"))
      .mockResolvedValueOnce(job("job-b", "test-clip02.mp4"));
    vi.mocked(getJob).mockResolvedValue(passed("job-b", "test-clip02.mp4"));
    render(<FinishBar projectId="p1" />);
    fireEvent.change(screen.getByLabelText(/upload media/i), {
      target: { files: [first, second] },
    });
    await waitFor(() => expect(ingestClip).toHaveBeenCalledTimes(2));
    expect(ingestClip).toHaveBeenNthCalledWith(1, "p1", first);
    expect(ingestClip).toHaveBeenNthCalledWith(2, "p1", second);
    expect(
      screen.queryByText(/the remaining clips were not uploaded/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/could not upload “test-clip01.mp4”/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /call wrap/i })).toBeEnabled());
  });

  it("says uploading while a clip is still being sent", () => {
    const file = new File(["x"], "take-01.mp4", { type: "video/mp4" });
    vi.mocked(ingestClip).mockReturnValue(new Promise(() => undefined));
    render(<FinishBar projectId="p1" />);
    fireEvent.change(screen.getByLabelText(/upload media/i), { target: { files: [file] } });
    expect(screen.getByText("uploading")).toBeInTheDocument();
    expect(screen.queryByText("accepting")).not.toBeInTheDocument();
  });

  it("promises highest-impact improvements in the budget copy", () => {
    render(<FinishBar projectId="p1" />);
    expect(
      screen.getByText(/highest-impact improvements that fit this budget/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/highest-priority improvements/i)).not.toBeInTheDocument();
  });

  it("keeps Call Wrap visibly disabled until clips are checked", () => {
    render(<FinishBar projectId="p1" />);
    const wrap = screen.getByRole("button", { name: /call wrap/i });
    expect(wrap).toBeDisabled();
    expect(wrap).toHaveAttribute("title", expect.stringMatching(/checked/i));
    expect(screen.getByText(/call wrap after every chosen clip has been checked/i)).toBeInTheDocument();
  });

  it("shows clips already on the project so the list matches progress after a refresh", () => {
    render(
      <FinishBar
        projectId="p1"
        existingJobs={[
          passed("job-1", "projects/p1/ingest/job-1/test-clip01.mp4"),
          passed("job-2", "projects/p1/ingest/job-2/test-clip02.mp4"),
          passed("job-3", "projects/p1/ingest/job-3/test-clip03.mp4"),
        ]}
      />,
    );
    expect(screen.queryByText(/no clips added yet/i)).not.toBeInTheDocument();
    expect(screen.getByText("test-clip01.mp4")).toBeInTheDocument();
    expect(screen.getByText("test-clip02.mp4")).toBeInTheDocument();
    expect(screen.getByText("test-clip03.mp4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /call wrap/i })).toBeEnabled();
  });

  it("keeps those project clips after Start over instead of pretending the bin is empty", () => {
    render(
      <FinishBar
        projectId="p1"
        existingJobs={[passed("job-1", "projects/p1/ingest/job-1/test-clip01.mp4")]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /start over/i }));
    expect(screen.getByText("test-clip01.mp4")).toBeInTheDocument();
    expect(screen.queryByText(/no clips added yet/i)).not.toBeInTheDocument();
  });
});
