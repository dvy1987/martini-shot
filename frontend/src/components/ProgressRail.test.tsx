import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProgressRail from "@/components/ProgressRail";
import { PROGRESS_STAGES } from "@/lib/journey";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ProgressRail", () => {
  it("renders every finishing stage in order", () => {
    render(<ProgressRail phase="mixing" />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("data-stage"))).toEqual(
      PROGRESS_STAGES.map((stage) => stage.phase),
    );
  });

  it("scrolls the rail so the active stage stays on screen", () => {
    const scrollTo = vi.fn();
    HTMLElement.prototype.scrollTo = scrollTo;
    render(<ProgressRail phase="executing" />);
    expect(screen.getByRole("listitem", { current: "step" })).toHaveAttribute(
      "data-stage",
      "executing",
    );
    expect(scrollTo).toHaveBeenCalled();
  });

  it("marks completed stages with a green top edge and the live stage yellow, with no bottom underline", () => {
    render(<ProgressRail phase="mixing" />);
    const upload = document.querySelector('[data-stage="uploading"]');
    const mix = document.querySelector('[data-stage="mixing"]');
    const delivery = document.querySelector('[data-stage="delivering"]');
    expect(upload).toHaveAttribute("data-tone", "complete");
    expect(upload?.className).toMatch(/border-signal/);
    expect(upload?.className).not.toMatch(/bg-signal/);
    expect(upload?.querySelector("[data-underline]")).toBeNull();
    expect(mix).toHaveAttribute("data-tone", "active");
    expect(mix?.className).toMatch(/border-tungsten/);
    expect(mix?.className).not.toMatch(/bg-tungsten/);
    expect(mix?.querySelector("[data-underline]")).toBeNull();
    expect(delivery).toHaveAttribute("data-tone", "pending");
    expect(delivery?.querySelector("[data-underline]")).toBeNull();
  });

  it("marks a failed stage with a red top edge and no bottom underline", () => {
    render(
      <ProgressRail
        phase="attention"
        jobs={[
          {
            job_id: "loud-fail",
            station: "loudness",
            status: "fail",
            project_id: "p",
            input_refs: [],
            attempts: 1,
          },
          {
            job_id: "ingest-ok",
            station: "ingest",
            status: "pass",
            project_id: "p",
            input_refs: [],
            attempts: 1,
          },
        ]}
      />,
    );
    const upload = document.querySelector('[data-stage="uploading"]');
    const mix = document.querySelector('[data-stage="mixing"]');
    expect(upload).toHaveAttribute("data-tone", "complete");
    expect(upload?.querySelector("[data-underline]")).toBeNull();
    expect(mix).toHaveAttribute("data-tone", "failed");
    expect(mix?.className).toMatch(/border-danger/);
    expect(mix?.className).not.toMatch(/bg-danger/);
    expect(mix?.querySelector("[data-underline]")).toBeNull();
  });
});
