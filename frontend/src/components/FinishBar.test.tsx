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
    fireEvent.change(screen.getByLabelText(/choose files/i), {
      target: { files: [first, second] },
    });
    await waitFor(() => expect(ingestClip).toHaveBeenNthCalledWith(1, "p1", first));
    expect(ingestClip).toHaveBeenNthCalledWith(2, "p1", second);
    expect(screen.queryByRole("button", { name: /add .* clip/i })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /start finishing/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /start finishing/i }));
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
    fireEvent.change(screen.getByLabelText(/choose files/i), {
      target: { files: [first, second] },
    });
    await waitFor(() => expect(screen.getByText("a.mp4")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: /start finishing/i })).toBeEnabled());
    fireEvent.dragStart(screen.getByRole("listitem", { name: /clip 2: b\.mp4/i }));
    fireEvent.drop(screen.getByRole("listitem", { name: /clip 1: a\.mp4/i }));
    fireEvent.click(screen.getByRole("button", { name: /start finishing/i }));
    await waitFor(() => expect(startFinish).toHaveBeenCalledWith("p1", 50_000_000, ["job-b", "job-a"]));
  });

  it("lists and accepts mp4s even when the browser leaves the mime type blank", async () => {
    const file = new File(["x"], "take-01.mp4", { type: "" });
    vi.mocked(ingestClip).mockResolvedValue(job("job-1", "take-01.mp4"));
    vi.mocked(getJob).mockResolvedValue(passed("job-1", "take-01.mp4"));
    render(<FinishBar projectId="p1" />);
    fireEvent.change(screen.getByLabelText(/choose files/i), { target: { files: [file] } });
    expect(screen.getByText("take-01.mp4")).toBeInTheDocument();
    await waitFor(() => expect(ingestClip).toHaveBeenCalledWith("p1", file));
  });
});
