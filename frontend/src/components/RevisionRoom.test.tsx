import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RevisionRoom from "@/components/RevisionRoom";

afterEach(cleanup);

describe("RevisionRoom", () => {
  it("saves a script edit and proposes regenerate for affected shots", async () => {
    const list = vi.fn().mockResolvedValue([
      {
        version_id: "scr-1",
        project_id: "p1",
        version_number: 1,
        text: "I'll take the usual.",
      },
    ]);
    const create = vi.fn().mockResolvedValue({
      version_id: "scr-2",
      project_id: "p1",
      version_number: 2,
      text: "I'll take the usual, extra hot.",
      based_on_version_id: "scr-1",
      affected: [{ affected_shot_ids: ["shot-table"], affected_languages: ["en"] }],
      agent: {
        name: "revision_room",
        decision: "propose_regeneration",
        rationale: "Line changed on the table shot.",
        cost_micros: 12,
      },
    });
    const regenerate = vi.fn().mockResolvedValue({
      approval_id: "appr-rev",
      status: "proposed",
    });
    render(
      <RevisionRoom
        projectId="p1"
        list={list}
        create={create}
        regenerate={regenerate}
      />,
    );
    expect(await screen.findByDisplayValue(/I'll take the usual/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/script/i), {
      target: { value: "I'll take the usual, extra hot." },
    });
    fireEvent.click(screen.getByRole("button", { name: /save script/i }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith("p1", {
        text: "I'll take the usual, extra hot.",
        based_on_version_id: "scr-1",
        consult_agent: true,
      }),
    );
    expect(await screen.findByText(/Line changed on the table shot/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /suggest updated clips/i }));
    await waitFor(() => expect(regenerate).toHaveBeenCalled());
    expect(await screen.findByText(/Suggestion created: appr-rev/)).toBeInTheDocument();
  });
});
