import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CommandPalette from "@/components/CommandPalette";
import type { PaletteCommand } from "@/lib/palette";

afterEach(cleanup);

const COMMANDS: PaletteCommand[] = [
  { id: "route:timeline", label: "Central station", hint: "Season board", kind: "route" },
  { id: "route:decisions", label: "Decisions", hint: "Screening room", kind: "route" },
  { id: "lens", label: "Toggle Lens", hint: "Reveal collapsed lanes", kind: "lens" },
];

describe("CommandPalette", () => {
  it("moves the highlight with arrows and activates with Enter", () => {
    const onSelect = vi.fn();
    render(
      <CommandPalette
        open
        commands={COMMANDS}
        returnFocusRef={{ current: null }}
        onClose={vi.fn()}
        onSelect={onSelect}
      />,
    );

    expect(screen.getByRole("option", { name: /central station/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: /decisions/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "route:decisions" }),
    );
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <CommandPalette
        open
        commands={COMMANDS}
        returnFocusRef={{ current: null }}
        onClose={onClose}
        onSelect={vi.fn()}
      />,
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
