import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/api/client";

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses the backend error envelope into an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ error: { code: "not_found", message: "no such job" } }), {
          status: 404,
          statusText: "Not Found",
        }),
      ),
    );

    const thrown = await apiFetch("/api/v1/jobs/j1").then(
      () => null,
      (error: unknown) => error,
    );

    expect(thrown).toBeInstanceOf(ApiError);
    const apiError = thrown as ApiError;
    expect(apiError.code).toBe("not_found");
    expect(apiError.message).toBe("no such job");
    expect(apiError.status).toBe(404);
  });

  it("falls back to status text when the error body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () => new Response("<html>boom</html>", { status: 502, statusText: "Bad Gateway" }),
      ),
    );

    const thrown = await apiFetch("/api/v1/projects").then(
      () => null,
      (error: unknown) => error,
    );

    expect(thrown).toBeInstanceOf(ApiError);
    expect((thrown as ApiError).code).toBe("unknown");
    expect((thrown as ApiError).message).toBe("Bad Gateway");
    expect((thrown as ApiError).status).toBe(502);
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([{ project_id: "p1" }]), { status: 200 })),
    );

    const data = await apiFetch<{ project_id: string }[]>("/api/v1/projects");
    expect(data[0]?.project_id).toBe("p1");
  });

  it("does not force JSON content-type on FormData bodies", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("Content-Type")).toBeNull();
      return new Response(JSON.stringify({ job_id: "job-1" }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const body = new FormData();
    body.append("file", new Blob([new Uint8Array([0, 1])]), "clip.mp4");
    await apiFetch("/api/v1/projects/g1/ingest", { method: "POST", body });
    expect(fetchMock).toHaveBeenCalled();
  });
});
