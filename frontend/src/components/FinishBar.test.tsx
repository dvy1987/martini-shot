import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FinishBar from "@/components/FinishBar";
import { ingestClip, startFinish } from "@/api/endpoints";

vi.mock("@/api/endpoints", () => ({
  ingestClip: vi.fn(),
  startFinish: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("FinishBar", () => {
  it("starts finishing with a dollar budget converted to micros", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: /finish/i }));
    await waitFor(() => expect(startFinish).toHaveBeenCalledWith("p1", 50_000_000));
  });

  it("uploads selected clips through ingest", async () => {
    vi.mocked(ingestClip).mockResolvedValue({
      job_id: "job-1",
      station: "ingest",
      project_id: "p1",
      input_refs: ["a.mp4"],
      status: "queued",
      attempts: 0,
    });
    render(<FinishBar projectId="p1" />);
    const input = screen.getByLabelText(/upload clips/i);
    const file = new File(["x"], "clip.mp4", { type: "video/mp4" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(ingestClip).toHaveBeenCalled());
  });
});
