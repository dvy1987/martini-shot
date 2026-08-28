import { describe, expect, it } from "vitest";

import { STATUS_META, statusMetaFor, statusMetaOrUnknown } from "@/lib/status";

describe("statusMetaFor", () => {
  it("maps known statuses to the film vocabulary", () => {
    expect(statusMetaFor("pass")?.term).toBe("Locked");
    expect(statusMetaFor("needs_human")?.term).toBe("Flagged");
    expect(statusMetaFor("throttled")?.hint).toContain("Spend Control");
  });

  it("returns null for unknown statuses", () => {
    expect(statusMetaFor("exploded")).toBeNull();
  });

  it("covers the full JobStatus union", () => {
    expect(Object.keys(STATUS_META)).toHaveLength(7);
  });
});

describe("statusMetaOrUnknown", () => {
  it("matches STATUS_META for known statuses", () => {
    expect(statusMetaOrUnknown("pass")).toEqual(STATUS_META.pass);
  });

  it("returns a truthful fallback instead of undefined for unknown statuses", () => {
    const meta = statusMetaOrUnknown("cancelled");
    expect(meta.term).toBe("Unrecognized");
    expect(meta.glyph).toBe("?");
    expect(meta.hint).toContain("cancelled");
  });
});
