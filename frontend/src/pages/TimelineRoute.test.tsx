import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getJob, getProject, getRunPulse, getWorklist, listDeliberations, listProjectShots, listProjects, listScripts } from "@/api/endpoints";
import TimelineRoute from "@/pages/TimelineRoute";
import type { Job, Project } from "@/types/api";

vi.mock("@/api/endpoints", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/endpoints")>();
  return {
    ...actual,
    getJob: vi.fn(),
    getProject: vi.fn(),
    getWorklist: vi.fn(),
    getRunPulse: vi.fn(),
    listProjectShots: vi.fn(),
    listProjects: vi.fn(),
    listScripts: vi.fn(),
    ingestClip: vi.fn(),
    startFinish: vi.fn(),
    listDeliberations: vi.fn(),
    patchWorklist: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const observedJob: Job = {
  job_id: "job-1",
  station: "ingest",
  project_id: "project-1",
  input_refs: [],
  status: "running",
  attempts: 1,
};

const observedProject: Project = {
  project_id: "project-1",
  title: "Observed season",
  created_at: "2026-08-28T00:00:00Z",
  station_counts: { ingest: 1 },
  health: "healthy",
  jobs: [observedJob],
};

function renderRoute() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TimelineRoute
        selectedProjectId="project-1"
        onSelectedProjectIdChange={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

function mockBoard() {
  vi.mocked(listProjects).mockResolvedValue([observedProject]);
  vi.mocked(getProject).mockResolvedValue(observedProject);
  vi.mocked(getJob).mockResolvedValue(observedJob);
  vi.mocked(listProjectShots).mockResolvedValue([]);
  vi.mocked(listScripts).mockResolvedValue([]);
  vi.mocked(getWorklist).mockRejectedValue(new Error("no worklist"));
  vi.mocked(getRunPulse).mockRejectedValue(new Error("no pulse"));
  vi.mocked(listDeliberations).mockResolvedValue([]);
}

describe("TimelineRoute investigation flow", () => {
  it("selects on the first click and opens the real job query on the second", async () => {
    mockBoard();
    renderRoute();

    const clip = await screen.findByRole("button", { name: /in the lab: job-1/i });
    fireEvent.click(clip);
    expect(getJob).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(clip);
    await waitFor(() => expect(getJob).toHaveBeenCalledWith("job-1"));
    expect(
      await screen.findByRole("dialog", { name: /investigation card job-1/i }),
    ).toBeInTheDocument();
  });

  it("renders the alternates lane from the real project shots endpoint", async () => {
    mockBoard();
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
    renderRoute();

    expect(await screen.findByText(/Scene 12 — chaser/)).toBeInTheDocument();
    expect(await screen.findByText("DRAFT")).toBeInTheDocument();
    expect(listProjectShots).toHaveBeenCalledWith("project-1");
  });

  it("renders run pulse headlines from the Grafana-backed endpoint", async () => {
    mockBoard();
    vi.mocked(getRunPulse).mockResolvedValue({
      project_id: "project-1",
      grafana: "ok",
      factory: { verdict: "healthy", headline: "Factory looks healthy." },
      burn: { headline: "No metered work on this dump yet.", top: [] },
      eta: { headline: "Nothing left in the worklist.", eta_seconds: 0, remaining_items: 0 },
      wheel: { items: [] },
    });
    renderRoute();
    expect(await screen.findByText(/factory looks healthy/i)).toBeInTheDocument();
    expect(getRunPulse).toHaveBeenCalledWith("project-1");
  });
});
