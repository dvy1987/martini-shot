import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import { asApiError, isNotFound } from "@/lib/errors";

describe("API error helpers", () => {
  it("treats only HTTP 404 as a missing resource", () => {
    expect(isNotFound(new ApiError("not_found", "gone", 404))).toBe(true);
    expect(isNotFound(new ApiError("unknown", "nope", 500))).toBe(false);
    expect(isNotFound(new Error("404"))).toBe(false);
  });

  it("preserves ApiError and wraps unknown failures", () => {
    const original = new ApiError("busy", "try later", 409);
    expect(asApiError(original)).toBe(original);
    const wrapped = asApiError("boom", "offline");
    expect(wrapped).toBeInstanceOf(ApiError);
    expect(wrapped.code).toBe("network_error");
    expect(wrapped.message).toBe("offline");
  });
});
