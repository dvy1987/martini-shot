import { describe, expect, it } from "vitest";

import { moveItem, reorder } from "./clipOrdering";

describe("clip ordering", () => {
  it("moves only within the staged list", () => {
    expect(reorder(["A", "B", "C"], 1, -1)).toEqual(["B", "A", "C"]);
    expect(reorder(["A", "B", "C"], 0, -1)).toEqual(["A", "B", "C"]);
  });

  it("drags a clip to any new slot", () => {
    expect(moveItem(["A", "B", "C"], 2, 0)).toEqual(["C", "A", "B"]);
    expect(moveItem(["A", "B", "C"], 0, 2)).toEqual(["B", "C", "A"]);
    expect(moveItem(["A", "B", "C"], 1, 1)).toEqual(["A", "B", "C"]);
    expect(moveItem(["A", "B", "C"], -1, 2)).toEqual(["A", "B", "C"]);
  });
});