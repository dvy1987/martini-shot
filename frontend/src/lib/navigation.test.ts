import { describe, expect, it } from "vitest";

import { ROUTES } from "@/lib/navigation";

describe("primary navigation", () => {
  it("names the home tab Central station", () => {
    expect(ROUTES.find((entry) => entry.id === "timeline")?.label).toBe("Central station");
  });

  it("offers exactly the finished tabs, in order", () => {
    // Unfinished screens (Studio on /changes, Reports on /reports) are not
    // offered as navigation — owner demo ruling 2026-09-09. Their routes
    // stay registered in App.tsx, so deep links keep working.
    expect(ROUTES.map((entry) => entry.id)).toEqual([
      "timeline",
      "suggestions",
      "decisions",
      "analytics",
    ]);
  });
});
