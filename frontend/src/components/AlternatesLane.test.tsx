import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AlternatesLane from "@/components/AlternatesLane";
import type { ShotRow } from "@/types/api";

afterEach(cleanup);

const shots: ShotRow[] = [
  {
    shot_id: "shot-1",
    title: "Scene 12 — chaser",
    locked: true,
    locked_by: "human-1",
    current_alternate_id: "alt-2",
    created_at: "2026-09-04T10:00:00Z",
    alternates: [
      {
        alternate_id: "alt-1",
        op: "extend",
        artifact_ref: "gs://bucket/alt-1.mp4",
        eval_scores: { flicker: 0.00727 },
        status: "retired",
        created_at: "2026-09-04T10:05:00Z",
      },
      {
        alternate_id: "alt-2",
        op: "extend",
        artifact_ref: "gs://bucket/alt-2.mp4",
        eval_scores: { flicker: 0.00465 },
        status: "continuity",
        created_at: "2026-09-04T10:06:00Z",
      },
    ],
  },
  {
    shot_id: "shot-2",
    title: "Scene 13 — reveal",
    locked: false,
    created_at: "2026-09-04T11:00:00Z",
    alternates: [
      {
        alternate_id: "alt-3",
        op: "extend",
        artifact_ref: "gs://bucket/alt-3.mp4",
        eval_scores: { flicker: 0.021 },
        status: "draft",
        created_at: "2026-09-04T11:05:00Z",
      },
    ],
  },
];

describe("AlternatesLane", () => {
  it("renders shots with their alternates as ghost cards, draft-first badges, and QC scores", () => {
    render(<AlternatesLane shots={shots} />);

    expect(screen.getByText(/Scene 12 — chaser/)).toBeInTheDocument();
    expect(screen.getByText(/Scene 13 — reveal/)).toBeInTheDocument();
    expect(screen.getByText("◼ Locked")).toBeInTheDocument();
    expect(screen.getByText("◇ Open")).toBeInTheDocument();
    expect(screen.getByText("DRAFT")).toBeInTheDocument();
    expect(screen.getByText("In continuity")).toBeInTheDocument();
    expect(screen.getByText("Retired")).toBeInTheDocument();
    expect(screen.getAllByText(/flicker/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/0.00727/)).toBeInTheDocument();
  });

  it("never claims an alternate replaced the cut: ghost cards, current one marked", () => {
    render(<AlternatesLane shots={shots} />);

    const current = screen.getByText(/In continuity/i).closest("[data-alternate-card]");
    expect(current).not.toBeNull();
    expect(current).toHaveAttribute("data-current", "true");
    expect(screen.getByText(/Scene 12 — chaser/).closest("[data-shot-card]")).toHaveAttribute(
      "data-locked",
      "true",
    );
  });

  it("plays the real signed media only after the operator asks", async () => {
    const fetchMediaUrl = vi.fn().mockResolvedValue("https://signed.example/alt-3.mp4");
    render(<AlternatesLane shots={shots} fetchMediaUrl={fetchMediaUrl} />);

    expect(screen.queryByRole("video")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /play alt-3/i }));

    await waitFor(() => expect(fetchMediaUrl).toHaveBeenCalledWith("alt-3"));
    const video = await screen.findByRole("video");
    expect(video).toHaveAttribute("src", "https://signed.example/alt-3.mp4");
  });

  it("renders its designed empty state when no shots exist yet", () => {
    render(<AlternatesLane shots={[]} />);

    expect(screen.getByText(/no generated clips yet/i)).toBeInTheDocument();
  });

  it("exposes Extend and Corrections on an open shot and blocks them on a locked cut", () => {
    render(<AlternatesLane shots={shots} />);

    expect(screen.getByRole("form", { name: /extend/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /propose extend/i })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: /corrections/i })).toBeInTheDocument();
    expect(
      screen.getByText(/locked cut — extend is blocked/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/locked cut — corrections are blocked/i),
    ).toBeInTheDocument();
  });
});
