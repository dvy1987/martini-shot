import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ClipReviewModal from "@/components/ClipReviewModal";
import type { JobClip } from "@/types/api";

afterEach(cleanup);

function clip(metadata: Record<string, unknown>): JobClip {
  return {
    job_id: "job-1",
    side: "after",
    clip_name: "cafe.mp4",
    url: "https://example.test/cafe.mp4",
    expires_in_minutes: 60,
    metadata,
  };
}

describe("ClipReviewModal", () => {
  it("shows the scene and reads the transcript over the after clip", () => {
    render(
      <ClipReviewModal
        clip={clip({
          duration_s: 4,
          scene: "A quiet cafe at dusk.",
          spoken_words: "Two coffees, please.",
        })}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("dialog", { name: /cafe.mp4/i })).toBeInTheDocument();
    expect(screen.getByText("Scene")).toBeInTheDocument();
    expect(screen.getByText("A quiet cafe at dusk.")).toBeInTheDocument();
    expect(screen.getByLabelText("Subtitles")).toHaveTextContent("Two coffees, please.");
  });
});
