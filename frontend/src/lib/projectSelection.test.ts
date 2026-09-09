import { describe, expect, it } from "vitest";

import { pickProjectId } from "./projectSelection";

describe("pickProjectId", () => {
  it("keeps the open project when it still exists", () => {
    expect(
      pickProjectId("show-b", [{ project_id: "show-a" }, { project_id: "show-b" }]),
    ).toBe("show-b");
  });

  it("uses the first project when none is open so Analytics is not blank", () => {
    expect(pickProjectId(null, [{ project_id: "show-a" }, { project_id: "show-b" }])).toBe(
      "show-a",
    );
  });

  it("returns none when the lab has no projects", () => {
    expect(pickProjectId("gone", [])).toBeNull();
    expect(pickProjectId(null, [])).toBeNull();
  });
});
