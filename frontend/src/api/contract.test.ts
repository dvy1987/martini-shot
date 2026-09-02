import { describe, expect, it } from "vitest";

/**
 * Live /api/v1 contract (C-1 remainder). Does not change the backend.
 * Skips when the API is not running so `npm run test` stays hermetic.
 */

const base =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";
const apiKey = (import.meta.env.VITE_API_KEY as string | undefined) || "";

async function backendUp(): Promise<boolean> {
  try {
    const response = await fetch(`${base}/api/v1/health`);
    return response.ok;
  } catch {
    return false;
  }
}

const live = await backendUp();

describe.skipIf(!live)("live /api/v1 contract", () => {
  it("exposes health without an API key (C-5.2)", async () => {
    const response = await fetch(`${base}/api/v1/health`);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok" });
  });

  it("rejects unauthenticated version with the error envelope (C-5.3)", async () => {
    const response = await fetch(`${base}/api/v1/version`);
    expect(response.status).toBe(401);
    const body = (await response.json()) as { error?: { code?: string; message?: string } };
    expect(body.error?.code).toBe("unauthorized");
    if (body.error?.message !== undefined) {
      expect(typeof body.error.message).toBe("string");
    }
  });

  it("does not leave other routes open without a key", async () => {
    const response = await fetch(`${base}/api/v1/projects`);
    expect(response.status).toBe(401);
    const body = (await response.json()) as { error?: { code?: string } };
    expect(body.error?.code).toBe("unauthorized");
  });

  it("SSE events use type/at/payload when authenticated", async () => {
    if (!apiKey) return;
    const url = `${base}/api/v1/projects/g1/events?api_key=${encodeURIComponent(apiKey)}`;
    const response = await fetch(url, { headers: { Accept: "text/event-stream" } });
    if (response.status === 401 || response.status === 404) return;
    expect(response.ok).toBe(true);
    expect(response.headers.get("content-type") || "").toContain("text/event-stream");
    const reader = response.body?.getReader();
    expect(reader).toBeTruthy();
    const chunk = await reader!.read();
    const text = new TextDecoder().decode(chunk.value);
    expect(text.includes(": ping") || text.includes("data:")).toBe(true);
    if (text.includes("data:")) {
      const line = text
        .split("\n")
        .find((row) => row.startsWith("data:"));
      if (line) {
        const event = JSON.parse(line.slice(5).trim()) as {
          type?: string;
          at?: string;
          payload?: unknown;
        };
        expect(typeof event.type).toBe("string");
        expect(typeof event.at).toBe("string");
        expect(event).toHaveProperty("payload");
      }
    }
    await reader!.cancel();
  });
});
