import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CameraLanguageControls from "@/components/CameraLanguageControls";
import type { ShotRow } from "@/types/api";

afterEach(cleanup);

const openShot: ShotRow = {
  shot_id: "shot-open",
  title: "Table two-shot",
  locked: false,
  current_alternate_id: "alt-1",
  alternates: [
    {
      alternate_id: "alt-1",
      artifact_ref: "gs://bucket/source.mp4",
      status: "draft",
    },
  ],
};

describe("CameraLanguageControls", () => {
  it("proposes a vocabulary move through H-0", async () => {
    const propose = vi.fn().mockResolvedValue({
      approval_id: "appr-cam",
      status: "proposed",
    });
    render(<CameraLanguageControls shot={openShot} propose={propose} />);
    fireEvent.click(screen.getByText(/steadicam/i));
    fireEvent.click(screen.getByRole("button", { name: /propose camera move/i }));
    await waitFor(() =>
      expect(propose).toHaveBeenCalledWith("shot-open", {
        source_uri: "gs://bucket/source.mp4",
        movement: "steadicam",
        reason: "Genre-aware suggestion: steadicam (model-named)",
      }),
    );
  });
});
