import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentNotesModal } from "@/components/AgentNotesModal";

afterEach(cleanup);

describe("AgentNotesModal", () => {
  it("shows a flowing note without repeating the four questions as headings", () => {
    const onClose = vi.fn();
    render(
      <AgentNotesModal
        title="Clip 1 · Fix audio"
        notes={{
          changed: "Mixed the soundtrack",
          problem: "They thought the clip was too quiet.",
          ignored: "They did not treat the weather as louder than the voices.",
          fixed: "They mixed toward the streaming target.",
          failed: "",
        }}
        onClose={onClose}
      />,
    );

    expect(screen.getByRole("dialog", { name: /clip 1 · fix audio/i })).toBeInTheDocument();
    expect(screen.queryByText("What they thought the problem was")).not.toBeInTheDocument();
    expect(screen.queryByText("What they ignored")).not.toBeInTheDocument();
    expect(screen.queryByText("What they fixed")).not.toBeInTheDocument();
    expect(screen.queryByText("Where they failed")).not.toBeInTheDocument();
    expect(screen.getByText("They thought the clip was too quiet.")).toBeInTheDocument();
    expect(screen.getByText(/weather as louder than the voices/i)).toBeInTheDocument();
    expect(screen.getByText(/streaming target/i)).toBeInTheDocument();
    expect(screen.getByText("This step succeeded.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
