import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { getProject, getWorklist, listProjectShots, listScripts } from "@/api/endpoints";
import ChangesRoute from "@/pages/ChangesRoute";

vi.mock("@/api/endpoints", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/endpoints")>();
  return {
    ...actual,
    listProjectShots: vi.fn(),
    listScripts: vi.fn(),
    getAlternateMedia: vi.fn(),
    createScriptVersion: vi.fn(),
    proposeRegenerateSpans: vi.fn(),
    getProject: vi.fn(),
    getWorklist: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderChanges(
  backend: "checking" | "up" | "down",
  selectedProjectId: string | null,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChangesRoute backend={backend} selectedProjectId={selectedProjectId} />
    </QueryClientProvider>,
  );
}

describe("ChangesRoute", () => {
  it("does not fetch shots when the backend is down", () => {
    renderChanges("down", "p1");
    expect(listProjectShots).not.toHaveBeenCalled();
    expect(screen.getByText(/changes are unavailable/i)).toBeInTheDocument();
  });

  it("asks for a timeline project before showing shot edits", () => {
    renderChanges("up", null);
    expect(listProjectShots).not.toHaveBeenCalled();
    expect(screen.getByText(/no project selected/i)).toBeInTheDocument();
  });

  it("lists new versions and script edits for the open project", async () => {
    vi.mocked(listScripts).mockResolvedValue([]);
    vi.mocked(getProject).mockResolvedValue({
      project_id: "p1",
      title: "p1",
      created_at: "2026-09-04T10:00:00Z",
      station_counts: {},
      health: "healthy",
      jobs: [],
    });
    vi.mocked(getWorklist).mockRejectedValue(new ApiError("not_found", "no such worklist", 404));
    vi.mocked(listProjectShots).mockResolvedValue([
      {
        shot_id: "shot-1",
        title: "Scene 12 — chaser",
        locked: true,
        current_alternate_id: null,
        created_at: "2026-09-04T10:00:00Z",
        alternates: [
          {
            alternate_id: "alt-1",
            op: "extend",
            artifact_ref: "gs://bucket/alt-1.mp4",
            eval_scores: { flicker: 0.00465 },
            status: "draft",
            created_at: "2026-09-04T10:05:00Z",
          },
        ],
      },
    ]);
    renderChanges("up", "p1");
    expect(await screen.findByText(/Scene 12 — chaser/)).toBeInTheDocument();
    expect(screen.getByText(/^studio$/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /new versions/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /update the script/i })).toBeInTheDocument();
    expect(listProjectShots).toHaveBeenCalledWith("p1");
  });
});
