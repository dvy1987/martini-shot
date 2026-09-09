import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DirectedEditStudio from "@/components/DirectedEditStudio";
import type {
  Approval,
  DirectedEditClarifyResult,
  DirectedEditTurn,
  Job,
  ShotRow,
  Worklist,
} from "@/types/api";

vi.mock("@/api/endpoints", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/endpoints")>();
  return {
    ...actual,
    getJobClip: vi.fn().mockResolvedValue({
      job_id: "job-relight-1",
      side: "after",
      clip_name: "Café scene",
      url: "https://signed.example/relit.mp4",
      expires_in_minutes: 60,
      metadata: {},
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function job(partial: Partial<Job> & Pick<Job, "job_id" | "station">): Job {
  return {
    project_id: "p1",
    input_refs: ["gs://bucket/cafe.mp4"],
    status: "pass",
    attempts: 1,
    ...partial,
  };
}

function shot(partial: Partial<ShotRow> & Pick<ShotRow, "shot_id">): ShotRow {
  return {
    title: null,
    locked: false,
    current_alternate_id: null,
    alternates: [],
    ...partial,
  };
}

function worklist(partial: Partial<Worklist> = {}): Worklist {
  return {
    project_id: "p1",
    budget_micros: 1,
    spent_micros: 0,
    status: "delivered",
    attendance: [],
    items: [],
    final_refs: [],
    original_refs: [],
    ...partial,
  };
}

const jobs = [
  job({ job_id: "job-in-1", station: "ingest", input_refs: ["gs://bucket/cafe.mp4"] }),
  job({
    job_id: "job-relight-1",
    station: "relight",
    input_refs: ["gs://bucket/cafe.mp4"],
    result: { alternate_id: "alt-existing", artifact_ref: "gs://bucket/relit.mp4" },
  }),
];

const shots = [shot({ shot_id: "shot-1", title: "Café scene" })];

const wl = worklist({
  source_by_shot: { "shot-1": "gs://bucket/cafe.mp4" },
  shot_order: { "shot-1": 0 },
});

describe("DirectedEditStudio", () => {
  it("shows the controls only once a clip is selected, and keeps Go disabled until a station, movement, or chat text is given", () => {
    render(
      <DirectedEditStudio projectId="p1" shots={shots} jobs={jobs} worklist={wl} />,
    );
    expect(screen.queryByRole("button", { name: /^go$/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /select café scene/i }));
    const go = screen.getByRole("button", { name: /^go$/i });
    expect(go).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /improve lighting/i }));
    expect(go).not.toBeDisabled();
  });

  it("reveals the 5 camera movement presets only once Camera movement is toggled on", () => {
    render(
      <DirectedEditStudio projectId="p1" shots={shots} jobs={jobs} worklist={wl} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /select café scene/i }));
    expect(screen.queryByRole("button", { name: /steadicam glide/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^camera movement$/i }));
    expect(screen.getByRole("button", { name: /steadicam glide/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /steadicam glide/i }));
    expect(screen.getByRole("button", { name: /^go$/i })).not.toBeDisabled();
  });

  it("asks a clarifying question, then combines the answer into a single generation call after Go", async () => {
    const clarify = vi
      .fn<
        (
          shotId: string,
          body: { stations: string[]; camera_movement?: string | null; chat_text: string; turns: DirectedEditTurn[] },
        ) => Promise<DirectedEditClarifyResult>
      >()
      .mockResolvedValueOnce({
        decision: "ask",
        question: "Warmer or cooler light?",
        final_intent: null,
        questions_asked: 0,
        max_questions: 5,
        cost_micros: 10,
      })
      .mockResolvedValueOnce({
        decision: "ready",
        question: null,
        final_intent: "Relight the café scene with a warm tone.",
        questions_asked: 1,
        max_questions: 5,
        cost_micros: 10,
      });
    const propose = vi.fn().mockResolvedValue({ approval_id: "appr-1", status: "proposed" });
    const decide = vi
      .fn<(approvalId: string, decision: "approve" | "reject") => Promise<Approval>>()
      .mockResolvedValue({
        approval_id: "appr-1",
        project_id: "p1",
        kind: "fix",
        title: "t",
        created_at: "now",
        status: "acting",
        job_id: "job-gen-1",
      });

    render(
      <DirectedEditStudio
        projectId="p1"
        shots={shots}
        jobs={jobs}
        worklist={wl}
        clarify={clarify}
        propose={propose}
        decide={decide}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /select café scene/i }));
    fireEvent.click(screen.getByRole("button", { name: /improve lighting/i }));
    fireEvent.change(screen.getByLabelText(/tell the agent what you want/i), {
      target: { value: "make it feel warmer" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^go$/i }));

    expect(await screen.findByText(/warmer or cooler light\?/i)).toBeInTheDocument();
    expect(clarify).toHaveBeenCalledWith("shot-1", {
      stations: ["relight"],
      camera_movement: null,
      chat_text: "make it feel warmer",
      turns: [],
    });

    fireEvent.change(screen.getByLabelText(/your answer/i), {
      target: { value: "warmer" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send answer/i }));

    await waitFor(() =>
      expect(clarify).toHaveBeenLastCalledWith("shot-1", {
        stations: ["relight"],
        camera_movement: null,
        chat_text: "make it feel warmer",
        turns: [{ question: "Warmer or cooler light?", answer: "warmer" }],
      }),
    );

    await waitFor(() =>
      expect(propose).toHaveBeenCalledWith("shot-1", {
        source_uri: "gs://bucket/cafe.mp4",
        intent: "Relight the café scene with a warm tone.",
        reason: "Studio directed edit",
      }),
    );
    await waitFor(() => expect(decide).toHaveBeenCalledWith("appr-1", "approve"));
    expect(await screen.findByText(/generating/i)).toBeInTheDocument();
  });

  it("shows the result and an add-to-final-cut action once the generation job passes", async () => {
    const clarify = vi.fn().mockResolvedValue({
      decision: "ready",
      question: null,
      final_intent: "Add a handheld camera move.",
      questions_asked: 0,
      max_questions: 5,
      cost_micros: 10,
    });
    const propose = vi.fn().mockResolvedValue({ approval_id: "appr-2", status: "proposed" });
    const decide = vi.fn().mockResolvedValue({
      approval_id: "appr-2",
      project_id: "p1",
      kind: "fix",
      title: "t",
      created_at: "now",
      status: "acting",
      job_id: "job-gen-2",
    });
    const promote = vi.fn().mockResolvedValue({ approval_id: "appr-promote", status: "proposed" });
    const fetchMediaUrl = vi.fn().mockResolvedValue("https://signed.example/alt-new.mp4");

    const { rerender } = render(
      <DirectedEditStudio
        projectId="p1"
        shots={shots}
        jobs={jobs}
        worklist={wl}
        clarify={clarify}
        propose={propose}
        decide={decide}
        promote={promote}
        fetchMediaUrl={fetchMediaUrl}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /select café scene/i }));
    fireEvent.click(screen.getByRole("button", { name: /camera movement/i }));
    fireEvent.click(screen.getByRole("button", { name: /whip pan/i }));
    fireEvent.click(screen.getByRole("button", { name: /^go$/i }));

    await waitFor(() => expect(decide).toHaveBeenCalledWith("appr-2", "approve"));

    const passedJobs = [
      ...jobs,
      job({
        job_id: "job-gen-2",
        station: "corrections",
        status: "pass",
        result: { alternate_id: "alt-new" },
      }),
    ];
    rerender(
      <DirectedEditStudio
        projectId="p1"
        shots={shots}
        jobs={passedJobs}
        worklist={wl}
        clarify={clarify}
        propose={propose}
        decide={decide}
        promote={promote}
        fetchMediaUrl={fetchMediaUrl}
      />,
    );

    const addButton = await screen.findByRole("button", { name: /add to final cut/i });
    fireEvent.click(addButton);

    await waitFor(() =>
      expect(promote).toHaveBeenCalledWith("shot-1", { alternate_id: "alt-new" }),
    );
    await waitFor(() =>
      expect(decide).toHaveBeenCalledWith("appr-promote", "approve"),
    );
    expect(await screen.findByText(/added to the final cut/i)).toBeInTheDocument();
  });
});
