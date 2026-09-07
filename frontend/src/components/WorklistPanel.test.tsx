import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorklistPanel, { nextWorklistOrder } from "@/components/WorklistPanel";
import type { Worklist, WorklistItem } from "@/types/api";

afterEach(cleanup);

const items: WorklistItem[] = [
  {
    id: "loud",
    station: "loudness",
    status: "passed",
    impact: "high",
    kind: "defect",
    summary: "unhearable",
  },
  {
    id: "ext",
    station: "extend",
    status: "waiting",
    impact: "medium",
    kind: "defect",
    summary: "dies mid-thought",
  },
  {
    id: "rel",
    station: "relight",
    status: "waiting",
    impact: "low",
    kind: "improvement",
    summary: "faces dark",
  },
];

const worklist: Worklist = {
  project_id: "p1",
  budget_micros: 50_000_000,
  spent_micros: 80_000,
  status: "waiting_for_budget",
  attendance: [],
  items,
  final_refs: [],
  original_refs: [],
};

describe("WorklistPanel", () => {
  it("ticks passed work green and lets the operator reorder waiting rows", () => {
    const onReorder = vi.fn();
    render(<WorklistPanel worklist={worklist} onReorder={onReorder} />);
    expect(screen.getByText(/locked/i).closest("td")?.className).toMatch(/text-signal/);
    fireEvent.click(screen.getByRole("button", { name: /move relight up/i }));
    expect(onReorder).toHaveBeenCalledWith(["loud", "rel", "ext"]);
  });
});

describe("nextWorklistOrder", () => {
  it("swaps waiting rows and leaves locked work in place", () => {
    expect(nextWorklistOrder(items, "rel", -1)).toEqual(["loud", "rel", "ext"]);
  });
});
