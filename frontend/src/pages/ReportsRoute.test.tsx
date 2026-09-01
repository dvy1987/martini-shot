import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { getMorningReport } from "@/api/endpoints";
import ReportsRoute from "@/pages/ReportsRoute";

vi.mock("@/api/endpoints", () => ({
  getMorningReport: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderReports(
  backend: "checking" | "up" | "down",
  selectedProjectId: string | null,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReportsRoute backend={backend} selectedProjectId={selectedProjectId} />
    </QueryClientProvider>,
  );
}

describe("ReportsRoute", () => {
  it("does not fetch when the backend is down", () => {
    renderReports("down", "p1");
    expect(getMorningReport).not.toHaveBeenCalled();
    expect(screen.getByText(/dailies are unreachable/i)).toBeInTheDocument();
  });

  it("treats a missing report as empty, not invented verdicts", async () => {
    vi.mocked(getMorningReport).mockRejectedValue(
      new ApiError("not_found", "no morning report", 404),
    );
    renderReports("up", "p1");
    expect(await screen.findByText(/no morning report yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/ingest/i)).not.toBeInTheDocument();
  });
});
