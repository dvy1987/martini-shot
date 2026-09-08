import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ExtendControls from "@/components/ExtendControls";
import type { ShotRow } from "@/types/api";

afterEach(cleanup);

const openShot: ShotRow = {
  shot_id: "shot-open",
  title: "Florist counter",
  locked: false,
  current_alternate_id: "alt-1",
  alternates: [
    {
      alternate_id: "alt-1",
      op: "coverage",
      artifact_ref: "gs://bucket/source.mp4",
      status: "draft",
    },
  ],
};

const shotWithPassingExtend: ShotRow = {
  shot_id: "shot-ready",
  title: "Florist counter",
  locked: false,
  current_alternate_id: "alt-src",
  alternates: [
    {
      alternate_id: "alt-src",
      op: "coverage",
      artifact_ref: "gs://bucket/source.mp4",
      status: "draft",
    },
    {
      alternate_id: "alt-ext",
      op: "extend",
      artifact_ref: "gs://bucket/ext-draft.mp4",
      eval_scores: { flicker: 0.003 },
      tier: "draft",
      status: "draft",
    },
  ],
};

const lockedShot: ShotRow = { ...openShot, shot_id: "shot-locked", locked: true };

describe("ExtendControls", () => {
  it("blocks extending a locked clip", () => {
    render(<ExtendControls shot={lockedShot} />);
    expect(screen.getByText(/This clip is locked\. Unlock it before creating an extended version/i)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /extend/i })).not.toBeInTheDocument();
  });

  it("proposes a draft extend through H-0", async () => {
    const proposeExtend = vi.fn().mockResolvedValue({
      approval_id: "appr-ext",
      status: "proposed",
    });
    render(<ExtendControls shot={openShot} proposeExtend={proposeExtend} />);

    fireEvent.click(screen.getByRole("button", { name: /suggest an extension/i }));

    await waitFor(() =>
      expect(proposeExtend).toHaveBeenCalledWith("shot-open", {
        source_uri: "gs://bucket/source.mp4",
        reason: "Continue the action naturally",
      }),
    );
    expect(await screen.findByText(/Suggestion created: appr-ext/)).toBeInTheDocument();
  });

  it("offers master only after a QC-passing extend draft", async () => {
    const proposeMaster = vi.fn().mockResolvedValue({
      approval_id: "appr-mst",
      status: "proposed",
    });
    render(
      <ExtendControls
        shot={openShot}
        proposeMaster={proposeMaster}
      />,
    );
    expect(screen.queryByRole("button", { name: /propose master/i })).not.toBeInTheDocument();

    cleanup();
    render(
      <ExtendControls shot={shotWithPassingExtend} proposeMaster={proposeMaster} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /propose master/i }));
    await waitFor(() =>
      expect(proposeMaster).toHaveBeenCalledWith("shot-ready", {
        op: "extend",
        source_uri: "gs://bucket/source.mp4",
        reason: "Master after passing draft QC",
      }),
    );
    expect(await screen.findByText(/H-0 appr-mst/)).toBeInTheDocument();
  });
});
