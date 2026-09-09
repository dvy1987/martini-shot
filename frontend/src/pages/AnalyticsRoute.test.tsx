import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getRunPulse, getWorklist, listProjects } from "@/api/endpoints";
import AnalyticsRoute from "@/pages/AnalyticsRoute";

vi.mock("@/api/endpoints", () => ({
  getRunPulse: vi.fn(),
  getWorklist: vi.fn(),
  listProjects: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderAnalytics(
  backend: "checking" | "up" | "down",
  selectedProjectId: string | null,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AnalyticsRoute backend={backend} selectedProjectId={selectedProjectId} />
    </QueryClientProvider>,
  );
}

describe("AnalyticsRoute", () => {
  it("does not fetch Grafana when the backend is down", () => {
    renderAnalytics("down", "p1");
    expect(getRunPulse).not.toHaveBeenCalled();
    expect(screen.getByText(/analytics are unavailable/i)).toBeInTheDocument();
  });

  it("asks for a timeline project before showing this run", async () => {
    vi.mocked(listProjects).mockResolvedValue([]);
    renderAnalytics("up", null);
    expect(await screen.findByText(/no project selected/i)).toBeInTheDocument();
    expect(getRunPulse).not.toHaveBeenCalled();
  });

  it("waits for the timeline project instead of showing a blank analytics tab", async () => {
    vi.mocked(listProjects).mockResolvedValue([
      {
        project_id: "p1",
        title: "storm-breaking",
        created_at: "2026-09-09T00:00:00Z",
        station_counts: {},
        health: "healthy",
        jobs: [],
      },
    ]);
    renderAnalytics("up", null);
    expect(await screen.findByText(/opening the same project as timeline/i)).toBeInTheDocument();
    expect(getRunPulse).not.toHaveBeenCalled();
    expect(screen.queryByText(/no project selected/i)).not.toBeInTheDocument();
  });

  it("watches the same project the timeline has open", async () => {
    vi.mocked(listProjects).mockResolvedValue([
      {
        project_id: "other-show",
        title: "other-show",
        created_at: "2026-09-09T00:00:00Z",
        station_counts: {},
        health: "healthy",
        jobs: [],
      },
      {
        project_id: "p1",
        title: "storm-breaking",
        created_at: "2026-09-09T00:00:00Z",
        station_counts: {},
        health: "healthy",
        jobs: [],
      },
    ]);
    vi.mocked(getWorklist).mockRejectedValue(new Error("no worklist"));
    vi.mocked(getRunPulse).mockResolvedValue({
      project_id: "p1",
      grafana: "ok",
      factory: { verdict: "healthy", headline: "Factory looks healthy." },
      burn: { headline: "No metered work on this dump yet.", top: [] },
      eta: { headline: "Nothing left in the worklist.", eta_seconds: 0, remaining_items: 0 },
      wheel: { items: [] },
      dashboards: [],
    });
    renderAnalytics("up", "p1");
    expect(await screen.findByText("storm-breaking")).toBeInTheDocument();
    expect(getRunPulse).toHaveBeenCalledWith("p1");
    expect(getRunPulse).not.toHaveBeenCalledWith("other-show");
  });

  it("renders this run from the run-pulse endpoint", async () => {
    vi.mocked(getWorklist).mockRejectedValue(new Error("no worklist"));
    vi.mocked(getRunPulse).mockResolvedValue({
      project_id: "p1",
      grafana: "ok",
      factory: { verdict: "healthy", headline: "Factory looks healthy." },
      burn: { headline: "No metered work on this dump yet.", top: [] },
      eta: { headline: "Nothing left in the worklist.", eta_seconds: 0, remaining_items: 0 },
      wheel: { items: [] },
      dashboards: [
        { title: "Station Health", url: "https://chipperm.grafana.net/d/pc-station-health" },
      ],
    });
    renderAnalytics("up", "p1");
    expect(await screen.findByText(/the house is running normally/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^this run$/i, level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /station health/i })).not.toBeInTheDocument();
    expect(getRunPulse).toHaveBeenCalledWith("p1");
  });
});
