import { describe, expect, it } from "vitest";
import { reorder } from "./clipOrdering";

describe("clip ordering", () => {
  it("moves only within the staged list", () => {
    expect(reorder(["A", "B", "C"], 1, -1)).toEqual(["B", "A", "C"]);
    expect(reorder(["A", "B", "C"], 0, -1)).toEqual(["A", "B", "C"]);
  });
});