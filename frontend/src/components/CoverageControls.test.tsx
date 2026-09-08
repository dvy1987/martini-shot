import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CoverageControls from "@/components/CoverageControls";
import type { ShotRow } from "@/types/api";

afterEach(cleanup);

const openShot: ShotRow = {
  shot_id: "shot-open",
  title: "Café sign",
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

describe("CoverageControls", () => {
  it("suggests another camera angle using the current clip", async () => {
    const propose = vi.fn().mockResolvedValue({
      approval_id: "appr-cov",
      status: "proposed",
    });
    render(<CoverageControls shot={openShot} propose={propose} />);
    fireEvent.click(screen.getByRole("button", { name: /suggest another angle/i }));
    await waitFor(() =>
      expect(propose).toHaveBeenCalledWith("shot-open", {
        source_uri: "gs://bucket/source.mp4",
        angle: "close_up",
        intent: "Same people, new angle",
        reference_uris: ["gs://bucket/source.mp4"],
        reason: "Looker-named coverage; clip is the subject reference",
      }),
    );
    expect(await screen.findByText(/Suggestion created: appr-cov/)).toBeInTheDocument();
  });
});
