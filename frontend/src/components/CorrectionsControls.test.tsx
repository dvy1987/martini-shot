import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CorrectionsControls from "@/components/CorrectionsControls";
import type { ShotRow } from "@/types/api";

afterEach(cleanup);

const openShot: ShotRow = {
  shot_id: "shot-open",
  title: "Café exterior",
  locked: false,
  current_alternate_id: "alt-1",
  alternates: [
    {
      alternate_id: "alt-1",
      op: "extend",
      artifact_ref: "gs://bucket/alt-1.mp4",
      status: "draft",
    },
  ],
};

const lockedShot: ShotRow = { ...openShot, shot_id: "shot-locked", locked: true };

describe("CorrectionsControls", () => {
  it("blocks corrections on a locked clip", () => {
    render(<CorrectionsControls shot={lockedShot} />);
    expect(screen.getByText(/This clip is locked\. Unlock it before creating a corrected version/i)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /fix something in this clip/i })).not.toBeInTheDocument();
  });

  it("proposes a correction through the real H-0 endpoint", async () => {
    const propose = vi.fn().mockResolvedValue({
      approval_id: "appr-1",
      status: "proposed",
      agent: { name: "corrections", decision: "propose_correction", rationale: "Bounded signage fix.", cost_micros: 12 },
    });
    render(<CorrectionsControls shot={openShot} propose={propose} />);

    fireEvent.change(screen.getByLabelText(/what should change/i), {
      target: { value: "Replace the café sign text with OPEN" },
    });
    fireEvent.click(screen.getByRole("button", { name: /suggest a correction/i }));

    await waitFor(() =>
      expect(propose).toHaveBeenCalledWith("shot-open", {
        source_uri: "gs://bucket/alt-1.mp4",
        intent: "Replace the café sign text with OPEN",
        protected_subjects: ["lead actor"],
        continuity_constraints: ["preserve framing"],
      }),
    );
    expect(await screen.findByText(/Suggestion created: appr-1/)).toBeInTheDocument();
    expect(screen.getByText(/Bounded signage fix/)).toBeInTheDocument();
  });
});
