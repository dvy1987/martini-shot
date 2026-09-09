import { describe, expect, it } from "vitest";

import { CAMERA_MOVEMENT_PRESETS, cameraMovementLabel } from "@/lib/cameraLanguagePresets";

describe("CAMERA_MOVEMENT_PRESETS", () => {
  it("offers exactly 5 curated presets, each with a real backend-matching id", () => {
    expect(CAMERA_MOVEMENT_PRESETS).toHaveLength(5);
    const ids = CAMERA_MOVEMENT_PRESETS.map((preset) => preset.id);
    expect(ids).toEqual([
      "handheld_shaky",
      "steadicam",
      "dolly_zoom",
      "crash_zoom",
      "whip_pan",
    ]);
  });

  it("gives every preset a human label and a description", () => {
    for (const preset of CAMERA_MOVEMENT_PRESETS) {
      expect(preset.label.length).toBeGreaterThan(0);
      expect(preset.description.length).toBeGreaterThan(0);
    }
  });
});

describe("cameraMovementLabel", () => {
  it("resolves a known preset id to its label", () => {
    expect(cameraMovementLabel("steadicam")).toBe("Steadicam glide");
  });

  it("falls back to the raw id for an unknown movement", () => {
    expect(cameraMovementLabel("drone_orbit")).toBe("drone_orbit");
  });
});
