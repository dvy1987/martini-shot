import { describe, expect, it } from "vitest";

import { ROUTES } from "@/lib/navigation";

describe("primary navigation", () => {
  it("names the home tab Central station", () => {
    expect(ROUTES.find((entry) => entry.id === "timeline")?.label).toBe("Central station");
  });

  it("names the shot-edit tab Studio", () => {
    expect(ROUTES.find((entry) => entry.id === "changes")?.label).toBe("Studio");
  });
});
