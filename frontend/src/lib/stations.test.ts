import { describe, expect, it } from "vitest";

import { stationDescription, stationName } from "@/lib/stations";

describe("station copy", () => {
  it("names the house-order stages the operator sees", () => {
    expect(stationName("upload")).toBe("Upload");
    expect(stationName("ingest")).toBe("Ingest");
    expect(stationName("loudness")).toBe("Fix audio");
    expect(stationName("pickups")).toBe("Pickups");
    expect(stationName("delivery")).toBe("Delivery");
  });

  it("explains what each house-order stage does", () => {
    expect(stationDescription("upload")).toMatch(/file opens/i);
    expect(stationDescription("ingest")).toMatch(/spoken words/i);
    expect(stationDescription("loudness")).toMatch(/mix/i);
    expect(stationDescription("pickups")).toMatch(/picture/i);
  });
});
