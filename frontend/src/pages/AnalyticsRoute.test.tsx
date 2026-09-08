import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getRunPulse, getWorklist } from "@/api/endpoints";
import AnalyticsRoute from "@/pages/AnalyticsRoute";

vi.mock("@/api/endpoints", () => ({
  getRunPulse: vi.fn(),
  getWorklist: vi.fn(),
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

  it("asks for a timeline project before showing Grafana watch", () => {
    renderAnalytics("up", null);
    expect(getRunPulse).not.toHaveBeenCalled();
    expect(screen.getByText(/no project selected/i)).toBeInTheDocument();
  });

  it("renders Grafana watch from the run-pulse endpoint", async () => {
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
    expect(await screen.findByText(/factory looks healthy/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^grafana watch$/i, level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /station health/i })).toHaveAttribute(
      "href",
      "https://chipperm.grafana.net/d/pc-station-health",
    );
    expect(getRunPulse).toHaveBeenCalledWith("p1");
  });
});
