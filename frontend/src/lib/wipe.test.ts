import { describe, expect, it } from "vitest";

import { clampWipe, wipeFromClientX, wipeFromKey } from "@/lib/wipe";

describe("wipe math", () => {
  it("clamps to 0–100 and rejects non-finite input", () => {
    expect(clampWipe(-10)).toBe(0);
    expect(clampWipe(140)).toBe(100);
    expect(clampWipe(42.5)).toBe(42.5);
    expect(clampWipe(Number.NaN)).toBe(0);
  });

  it("maps pointer x inside the track to a percent", () => {
    expect(wipeFromClientX(150, 100, 200)).toBe(25);
    expect(wipeFromClientX(50, 100, 200)).toBe(0);
    expect(wipeFromClientX(400, 100, 200)).toBe(100);
    expect(wipeFromClientX(150, 100, 0)).toBe(0);
  });

  it("nudges with arrow keys and jumps with Home/End", () => {
    expect(wipeFromKey(50, "ArrowLeft")).toBe(45);
    expect(wipeFromKey(50, "ArrowRight")).toBe(55);
    expect(wipeFromKey(12, "Home")).toBe(0);
    expect(wipeFromKey(12, "End")).toBe(100);
    expect(wipeFromKey(12, "a")).toBe(12);
  });
});
