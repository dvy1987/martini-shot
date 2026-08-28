import { describe, expect, it } from "vitest";

import { cost, relativeTime, timecode, utcClock } from "@/lib/formatters";

describe("timecode", () => {
  it("formats zero as 00:00:00.000", () => {
    expect(timecode(0)).toBe("00:00:00.000");
  });

  it("renders hours, minutes, seconds, and millis", () => {
    expect(timecode(3_661_001)).toBe("01:01:01.001");
  });

  it("clamps negative durations", () => {
    expect(timecode(-5)).toBe("00:00:00.000");
  });
});

describe("utcClock", () => {
  it("renders the UTC wall clock", () => {
    expect(utcClock(new Date("2026-08-28T03:07:09Z"))).toBe("03:07:09");
  });
});

describe("cost", () => {
  it("formats micro-dollar amounts", () => {
    expect(cost(1_500_000)).toBe("$1.50");
  });

  it("keeps sub-cent precision", () => {
    expect(cost(250_000)).toBe("$0.2500");
  });

  it("formats zero", () => {
    expect(cost(0)).toBe("$0.00");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-08-28T12:00:00Z");

  it("says just now within 45 seconds", () => {
    expect(relativeTime("2026-08-28T11:59:30Z", now)).toBe("just now");
  });

  it("renders minutes and hours", () => {
    expect(relativeTime("2026-08-28T11:40:00Z", now)).toBe("20m ago");
    expect(relativeTime("2026-08-28T09:00:00Z", now)).toBe("3h ago");
  });

  it("renders days and tolerates invalid input", () => {
    expect(relativeTime("2026-08-26T12:00:00Z", now)).toBe("2d ago");
    expect(relativeTime("not-a-date", now)).toBe("unknown");
  });
});
