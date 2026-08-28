import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getJob, getProject, listProjects } from "@/api/endpoints";
import TimelineRoute from "@/pages/TimelineRoute";
import type { Job, Project } from "@/types/api";

vi.mock("@/api/endpoints", () => ({
  getJob: vi.fn(),
  getProject: vi.fn(),
  listProjects: vi.fn(),
}));

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

describe("TimelineRoute investigation flow", () => {
  it("selects on the first click and opens the real job query on the second", async () => {
    vi.mocked(listProjects).mockResolvedValue([observedProject]);
    vi.mocked(getProject).mockResolvedValue(observedProject);
    vi.mocked(getJob).mockResolvedValue(observedJob);
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
});