import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { createProject, getJob, getProject, getWorklist, listDeliberations, listProjectShots, listProjects, listScripts, renameProject } from "@/api/endpoints";
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
    renameProject: vi.fn(),
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
  vi.mocked(getWorklist).mockRejectedValue(new ApiError("not_found", "no worklist", 404));
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

  it("names house-order stages on current progress and hides a missing work plan", async () => {
    mockBoard();
    renderRoute();
    expect((await screen.findAllByText("Upload")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ingest").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fix audio").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pickups").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Review clips").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Plan work").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Execute").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Delivery").length).toBeGreaterThan(0);
    expect(screen.getByRole("list", { name: /finishing stages/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Stage in progress")).toBeInTheDocument();
    expect(screen.queryByText(/check files/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/the current work plan could not be loaded/i)).not.toBeInTheDocument();
  });

  it("lets the operator start a new project when none exist", async () => {
    vi.mocked(listProjects).mockResolvedValue([]);
    vi.mocked(createProject).mockResolvedValue({
      project_id: "project-new",
      title: "Cafe pickup",
      created_at: "2026-09-08T00:00:00Z",
      station_counts: {},
      health: "healthy",
      jobs: [],
    });
    renderRoute();
    expect(await screen.findByRole("button", { name: /start a new project/i })).toBeInTheDocument();
    expect(screen.getByText(/no projects yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start a new project/i }));
    expect(createProject).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/new project name/i), {
      target: { value: "Cafe pickup" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalledWith("Cafe pickup"));
  });

  it("asks for a name after New project before opening the show", async () => {
    const created: Project = {
      project_id: "project-new",
      title: "Night exteriors",
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
    fireEvent.click(await screen.findByRole("button", { name: /new project/i }));
    expect(createProject).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/new project name/i), {
      target: { value: "Night exteriors" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalledWith("Night exteriors"));
    await waitFor(() => expect(onSelectedProjectIdChange).toHaveBeenCalledWith("project-new"));
  });

  it("renames the open project", async () => {
    const renamed: Project = {
      ...observedProject,
      title: "Night exteriors",
    };
    mockBoard();
    vi.mocked(renameProject).mockResolvedValue(renamed);
    renderRoute();
    fireEvent.click(await screen.findByRole("button", { name: /rename project/i }));
    expect(screen.queryByRole("button", { name: /^rename project$/i })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "Night exteriors" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save name/i }));
    await waitFor(() => expect(renameProject).toHaveBeenCalledWith("project-1", "Night exteriors"));
  });

  it("does not mark upload complete from another project's clips", async () => {
    mockBoard();
    vi.mocked(getProject).mockResolvedValue({
      ...observedProject,
      station_counts: {},
      jobs: [
        {
          ...observedJob,
          job_id: "job-foreign",
          project_id: "other-project",
          status: "pass",
          input_refs: ["projects/other-project/ingest/job-foreign/test-clip01.mp4"],
        },
      ],
    });
    renderRoute();
    expect(await screen.findByText("Get started")).toBeInTheDocument();
    expect(screen.queryByText("Upload complete")).not.toBeInTheDocument();
    expect(screen.getByText(/no clips added yet/i)).toBeInTheDocument();
  });

  it("does not put another project's jobs on the timeline", async () => {
    mockBoard();
    vi.mocked(getProject).mockResolvedValue({
      ...observedProject,
      jobs: [
        observedJob,
        {
          ...observedJob,
          job_id: "job-foreign",
          project_id: "other-project",
          status: "pass",
        },
      ],
    });
    renderRoute();
    expect(await screen.findByRole("button", { name: /in progress: job-1/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /complete: job-foreign/i })).not.toBeInTheDocument();
  });
});
