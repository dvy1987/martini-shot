import { describe, expect, it } from "vitest";

import { canDecide, spendSlate, SPEND_SLATE } from "@/lib/approvals";

describe("approval presentation", () => {
  it("labels only spend-kind cards with the accounting slate", () => {
    expect(spendSlate("spend")).toBe(SPEND_SLATE);
    expect(spendSlate("fix")).toBeNull();
  });

  it("allows a decision only while the case is still proposed", () => {
    expect(canDecide("proposed")).toBe(true);
    expect(canDecide("approved")).toBe(false);
    expect(canDecide("rejected")).toBe(false);
    expect(canDecide("acting")).toBe(false);
    expect(canDecide("resolved")).toBe(false);
  });
});
