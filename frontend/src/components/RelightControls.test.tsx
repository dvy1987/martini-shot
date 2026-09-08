import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RelightControls from "@/components/RelightControls";
import type { ShotRow } from "@/types/api";

afterEach(cleanup);

const openShot: ShotRow = {
  shot_id: "shot-open",
  title: "Café table",
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

describe("RelightControls", () => {
  it("blocks relight on a locked cut", () => {
    render(<RelightControls shot={lockedShot} />);
    expect(screen.getByText(/locked cut/i)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /relight/i })).not.toBeInTheDocument();
  });

  it("proposes a named preset through H-0", async () => {
    const propose = vi.fn().mockResolvedValue({
      approval_id: "appr-rlt",
      status: "proposed",
    });
    render(<RelightControls shot={openShot} propose={propose} />);
    fireEvent.click(screen.getByText(/noir/i));
    fireEvent.click(screen.getByRole("button", { name: /propose relight/i }));
    await waitFor(() =>
      expect(propose).toHaveBeenCalledWith("shot-open", {
        source_uri: "gs://bucket/alt-1.mp4",
        preset: "noir",
        reason: "Looker-named or operator-picked noir",
      }),
    );
    expect(await screen.findByText(/H-0 appr-rlt/)).toBeInTheDocument();
  });
});
