import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { getJobClip } from "@/api/endpoints";
import ClipThumb from "@/components/ClipThumb";

vi.mock("@/api/endpoints", () => ({
  getJobClip: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ClipThumb", () => {
  it("still plays the clip through the lab media path when GCS cannot sign", async () => {
    vi.mocked(getJobClip).mockRejectedValue(
      new ApiError("unknown", "clip could not be signed", 502),
    );
    render(
      <ClipThumb jobId="job-1" side="before" label="test-clip01.mp4" onOpen={vi.fn()} />,
    );
    const button = await screen.findByRole("button", { name: /open test-clip01\.mp4/i });
    expect(button.querySelector("video")).toHaveAttribute(
      "src",
      expect.stringContaining("/api/v1/jobs/job-1/clip/before/media"),
    );
    expect(screen.queryByText(/could not be signed/i)).not.toBeInTheDocument();
  });
});
