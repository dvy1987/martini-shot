import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InvestigationDrawer from "@/components/InvestigationDrawer";
import type { Deliberation, Job } from "@/types/api";

afterEach(cleanup);

const inspectedJob: Job = {
  job_id: "job-1",
  station: "ingest",
  project_id: "project-1",
  input_refs: ["s3://rushes/scene-01.mov", "s3://rushes/scene-01.json"],
  status: "fail",
  attempts: 3,
  cost_micros: 4200,
  error: { code: "QC_FLICKER", message: "Flicker exceeds threshold." },
};

describe("InvestigationDrawer", () => {
  it("focuses the case file, keeps folds closed, and progressively reveals details", async () => {
    render(
      <InvestigationDrawer
        open
        job={inspectedJob}
        isLoading={false}
        error={null}
        returnFocusRef={{ current: null }}
        onClose={vi.fn()}
      />,
    );

    const drawer = screen.getByRole("dialog", { name: /investigation card/i });
    await waitFor(() => expect(drawer).toHaveFocus());

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: /show transcript/i })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByRole("button", { name: /close investigation drawer/i })).toHaveFocus();

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("$0.0042")).toBeInTheDocument();
    expect(screen.queryByText("s3://rushes/scene-01.mov")).not.toBeInTheDocument();
    expect(screen.queryByText(/"job_id"/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show evidence/i }));
    expect(screen.getByText("s3://rushes/scene-01.mov")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show transcript/i }));
    expect(screen.getByText(/"job_id": "job-1"/)).toBeInTheDocument();
  });

  it("closes from Escape and scrim clicks", () => {
    const onClose = vi.fn();
    render(
      <InvestigationDrawer
        open
        job={inspectedJob}
        isLoading={false}
        error={null}
        returnFocusRef={{ current: null }}
        onClose={onClose}
      />,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: /close investigation backdrop/i }));

    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("returns focus to the triggering control when the drawer closes", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      const triggerRef = useRef<HTMLButtonElement | null>(null);
      return (
        <>
          <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>
            Open job
          </button>
          <InvestigationDrawer
            open={open}
            job={open ? inspectedJob : null}
            isLoading={false}
            error={null}
            returnFocusRef={triggerRef}
            onClose={() => setOpen(false)}
          />
        </>
      );
    }

    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open job" });
    fireEvent.click(trigger);
    await waitFor(() => expect(screen.getByRole("dialog")).toHaveFocus());

    fireEvent.click(screen.getByRole("button", { name: /close investigation drawer$/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: /show transcript/i })).toHaveFocus();
    await waitFor(() => expect(trigger).toHaveFocus());
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows truthful loading and API error states", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <InvestigationDrawer
        open
        job={null}
        isLoading
        error={null}
        returnFocusRef={{ current: null }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/loading investigation/i)).toBeInTheDocument();

    rerender(
      <InvestigationDrawer
        open
        job={null}
        isLoading={false}
        error={{ code: "JOB_NOT_FOUND", message: "Job record is unavailable." }}
        returnFocusRef={{ current: null }}
        onRetry={onRetry}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("JOB_NOT_FOUND")).toBeInTheDocument();
    expect(screen.getByText("Job record is unavailable.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry case file/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders an unknown API status truthfully instead of crashing", () => {
    render(
      <InvestigationDrawer
        open
        job={{ ...inspectedJob, status: "cancelled" } as unknown as Job}
        isLoading={false}
        error={null}
        returnFocusRef={{ current: null }}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Unknown status")).toBeInTheDocument();
    expect(screen.getByText(/cancelled/)).toBeInTheDocument();
  });

  it("renders the agent deliberation panel when a deliberation is provided, and stays silent without one", () => {
    const deliberation: Deliberation = {
      cycle_id: "cyc-1",
      case_id: "case-1",
      created_at: "2026-09-04T00:00:00Z",
      trigger: { kind: "job_failed", job_id: "job-1", project_id: "project-1" },
      specialists: ["reliability_investigator"],
      verdict: { rejected: [], approved_specialists: ["reliability_investigator"] },
      recommendation: {
        ranked_actions: [
          {
            command_name: "retry_job",
            args: { job_id: "job-1" },
            cost_estimate_micros: 500,
            reversible: true,
          },
        ],
        dissent: [],
      },
      status: "proposed",
    };
    const { rerender } = render(
      <InvestigationDrawer
        open
        job={inspectedJob}
        isLoading={false}
        error={null}
        deliberation={deliberation}
        returnFocusRef={{ current: null }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/Agent deliberation/i)).toBeInTheDocument();
    expect(screen.getByText(/retry_job/)).toBeInTheDocument();

    rerender(
      <InvestigationDrawer
        open
        job={inspectedJob}
        isLoading={false}
        error={null}
        deliberation={null}
        returnFocusRef={{ current: null }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Agent deliberation/i)).not.toBeInTheDocument();
  });
});