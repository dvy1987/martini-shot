import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createProject, getJob, getProject, getWorklist, listDeliberations, listProjectShots, listProjects, listScripts } from "@/api/endpoints";
import TimelineRoute from "@/pages/TimelineRoute";
import type { Job, Project } from "@/types/api";

vi.mock("@/api/endpoints", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/endpoints")>();
  return {
    ...actual,
    getJob: vi.fn(),
    getProject: vi.fn(),
    getWorklist: vi.fn(),
    listProjectShots: vi.fn(),
    listProjects: vi.fn(),
    createProject: vi.fn(),
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
  vi.mocked(listDeliberations).mockResolvedValue([]);
}

describe("TimelineRoute investigation flow", () => {
  it("selects on the first click and opens the real job query on the second", async () => {
    mockBoard();
    renderRoute();

    const clip = await screen.findByRole("button", { name: /in progress: job-1/i });
    fireEvent.click(clip);
    expect(getJob).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /grafana watch/i })).not.toBeInTheDocument();

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
    expect(await screen.findByText(/draft/i)).toBeInTheDocument();
    expect(listProjectShots).toHaveBeenCalledWith("project-1");
  });

  it("lets the operator start a new show when none exist", async () => {
    vi.mocked(listProjects).mockResolvedValue([]);
    renderRoute();
    expect(await screen.findByRole("button", { name: /start a new show/i })).toBeInTheDocument();
    expect(screen.getByText(/no shows yet/i)).toBeInTheDocument();
  });

  it("opens a new show from the project picker and selects it", async () => {
    const created: Project = {
      project_id: "show-new",
      title: "Untitled show",
      created_at: "2026-09-08T00:00:00Z",
      station_counts: {},
      health: "healthy",
      jobs: [],
    };
    mockBoard();
    vi.mocked(createProject).mockResolvedValue(created);
    const onSelectedProjectIdChange = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <TimelineRoute
          selectedProjectId="project-1"
          onSelectedProjectIdChange={onSelectedProjectIdChange}
        />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: /new show/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalled());
    await waitFor(() => expect(onSelectedProjectIdChange).toHaveBeenCalledWith("show-new"));
  });
});
