import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getWorklist } from "@/api/endpoints";
import SuggestionsRoute from "@/pages/SuggestionsRoute";
import type { Worklist } from "@/types/api";

vi.mock("@/api/endpoints", () => ({
  getWorklist: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderSuggestions(
  backend: "checking" | "up" | "down",
  selectedProjectId: string | null,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SuggestionsRoute backend={backend} selectedProjectId={selectedProjectId} />
    </QueryClientProvider>,
  );
}

function worklist(partial: Partial<Worklist> = {}): Worklist {
  return {
    project_id: "p1",
    budget_micros: 5_000_000,
    spent_micros: 0,
    status: "inspecting",
    attendance: [],
    items: [],
    final_refs: [],
    original_refs: [],
    ...partial,
  };
}

describe("SuggestionsRoute", () => {
  it("does not fetch when the backend is down", () => {
    renderSuggestions("down", "p1");
    expect(getWorklist).not.toHaveBeenCalled();
    expect(screen.getByText(/suggestions are unavailable/i)).toBeInTheDocument();
  });

  it("asks for a timeline project before showing suggestions", () => {
    renderSuggestions("up", null);
    expect(getWorklist).not.toHaveBeenCalled();
    expect(screen.getByText(/no project selected/i)).toBeInTheDocument();
  });

  it("waits until mix and pickups finish before listing leftover suggestions", async () => {
    vi.mocked(getWorklist).mockResolvedValue(
      worklist({
        phase: "cleanup",
        items: [{ id: "loudness::shot-a", station: "loudness", status: "running" }],
      }),
    );
    renderSuggestions("up", "p1");
    expect(await screen.findByRole("heading", { name: /not yet/i })).toBeInTheDocument();
    expect(screen.queryByText(/keep rolling/i)).not.toBeInTheDocument();
  });

  it("lists leftover suggestions as stations report them", async () => {
    vi.mocked(getWorklist).mockResolvedValue(
      worklist({
        phase: "consulting",
        attendance: [
          {
            station: "extend",
            agent: "extend-agent",
            status: "needs_work",
            impact: "medium",
            kind: "defect",
            summary: "Keep rolling past the cut",
            cost_estimate_micros: 3_000_000,
            shot_id: "shot-a",
          },
          {
            station: "relight",
            agent: "relight-agent",
            status: "empty",
            impact: "none",
            kind: "none",
            summary: "",
            cost_estimate_micros: 0,
            shot_id: "shot-a",
          },
        ],
      }),
    );
    renderSuggestions("up", "p1");
    expect(await screen.findByText(/keep rolling past the cut/i)).toBeInTheDocument();
    expect(screen.getByText(/incoming suggestions/i)).toBeInTheDocument();
    expect(screen.queryByText(/estimated cutoff/i)).not.toBeInTheDocument();
  });

  it("shows stack rank and a budget cutoff after the orchestrator plans the work", async () => {
    vi.mocked(getWorklist).mockResolvedValue(
      worklist({
        phase: "planning",
        status: "waiting_for_budget",
        items: [
          {
            id: "extend::shot-a",
            station: "extend",
            status: "waiting",
            summary: "Keep rolling",
            cost_estimate_micros: 3_000_000,
          },
          {
            id: "relight::shot-a",
            station: "relight",
            status: "waiting",
            summary: "Lift faces",
            cost_estimate_micros: 1_500_000,
          },
          {
            id: "coverage::shot-a",
            station: "coverage",
            status: "waiting",
            summary: "Add a closer angle",
            cost_estimate_micros: 2_000_000,
          },
        ],
      }),
    );
    renderSuggestions("up", "p1");
    expect(await screen.findByText(/ranked plan/i)).toBeInTheDocument();
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getByText("02")).toBeInTheDocument();
    expect(screen.getByText("03")).toBeInTheDocument();
    expect(screen.getByText(/estimated cutoff/i)).toBeInTheDocument();
    expect(screen.getByText(/add a closer angle/i).closest("li")?.className).toMatch(
      /opacity/,
    );
  });

  it("moves the cutoff when a planned step costs more than expected", async () => {
    vi.mocked(getWorklist).mockResolvedValue(
      worklist({
        status: "waiting_for_budget",
        spent_micros: 4_200_000,
        items: [
          {
            id: "extend::shot-a",
            station: "extend",
            status: "passed",
            summary: "Keep rolling",
            cost_estimate_micros: 3_000_000,
            cost_actual_micros: 4_200_000,
          },
          {
            id: "relight::shot-a",
            station: "relight",
            status: "waiting",
            summary: "Lift faces",
            cost_estimate_micros: 1_500_000,
          },
          {
            id: "coverage::shot-a",
            station: "coverage",
            status: "waiting",
            summary: "Add a closer angle",
            cost_estimate_micros: 500_000,
          },
        ],
      }),
    );
    renderSuggestions("up", "p1");
    expect(await screen.findByText(/estimated cutoff/i)).toBeInTheDocument();
    expect(screen.getByText(/lift faces/i).closest("li")?.className).toMatch(/opacity/);
    expect(screen.getByText(/add a closer angle/i).closest("li")?.className).toMatch(
      /opacity/,
    );
  });
});
