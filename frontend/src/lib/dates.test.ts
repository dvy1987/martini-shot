import { describe, expect, it } from "vitest";

import { utcDateStamp } from "@/lib/dates";

describe("utcDateStamp", () => {
  it("returns the UTC calendar day", () => {
    expect(utcDateStamp(new Date("2026-09-01T23:30:00.000Z"))).toBe("2026-09-01");
    expect(utcDateStamp(new Date("2026-09-01T00:00:00.000Z"))).toBe("2026-09-01");
  });
});
