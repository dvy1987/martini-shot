/** API client auth-header tests (owner sign-in gate plumbing). */

import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, setGoogleIdToken } from "./client";

describe("apiFetch auth headers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setGoogleIdToken("");
  });

  it("sends the Google ID token header for owner-class writes once signed in", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    setGoogleIdToken("jwt-credential");
    await apiFetch("/api/v1/settings", { method: "PATCH", body: "{}" });

    const headers = new Headers(fetchMock.mock.calls[0]![1]!.headers);
    expect(headers.get("X-Google-ID-Token")).toBe("jwt-credential");
  });

  it("sends no Google header when not signed in", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/settings");

    const headers = new Headers(fetchMock.mock.calls[0]![1]!.headers);
    expect(headers.get("X-Google-ID-Token")).toBeNull();
  });
});

