import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { listApprovals, decideApproval } from "@/api/endpoints";
import ApprovalsRoute from "@/pages/ApprovalsRoute";
import type { Approval } from "@/types/api";

vi.mock("@/api/endpoints", () => ({
  listApprovals: vi.fn(),
  decideApproval: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const proposed: Approval = {
  approval_id: "ap-1",
  project_id: "p1",
  kind: "spend",
  title: "Hourly cap",
  created_at: "2026-09-01T00:00:00Z",
  status: "proposed",
  cost_delta_micros: 4000,
};

function renderApprovals(backend: "checking" | "up" | "down") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ApprovalsRoute backend={backend} />
    </QueryClientProvider>,
  );
}

describe("ApprovalsRoute", () => {
  it("does not fetch or write when the backend is unreachable", () => {
    renderApprovals("down");
    expect(listApprovals).not.toHaveBeenCalled();
    expect(decideApproval).not.toHaveBeenCalled();
    expect(screen.getByText(/screening room is dark/i)).toBeInTheDocument();
  });

  it("does not POST a decision when the queue is honestly empty", async () => {
    vi.mocked(listApprovals).mockResolvedValue([]);
    renderApprovals("up");
    expect(await screen.findByText(/no cards in the screening room/i)).toBeInTheDocument();
    expect(decideApproval).not.toHaveBeenCalled();
  });

  it("posts decideApproval with the observed id", async () => {
    vi.mocked(listApprovals).mockResolvedValue([proposed]);
    vi.mocked(decideApproval).mockResolvedValue({ ...proposed, status: "approved" });
    renderApprovals("up");

    fireEvent.click(await screen.findByRole("button", { name: /^approve$/i }));
    await waitFor(() => expect(decideApproval).toHaveBeenCalledWith("ap-1", "approve"));
    expect(screen.getByText("PRODUCTION ACCOUNTING")).toBeInTheDocument();
  });
});
