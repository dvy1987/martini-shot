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
});
