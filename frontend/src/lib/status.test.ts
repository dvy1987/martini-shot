import { describe, expect, it } from "vitest";

import { STATUS_META, statusMetaFor } from "@/lib/status";

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
