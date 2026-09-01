import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import SlateDeck from "@/components/SlateDeck";

afterEach(cleanup);

beforeEach(() => {
  window.localStorage.clear();
});

describe("SlateDeck", () => {
  it("writes pc.seen.welcome when Skip is clicked", async () => {
    render(<SlateDeck id="welcome" replayToken={0} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^skip$/i }));
    expect(window.localStorage.getItem("pc.seen.welcome")).toBe("1");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("stays dismissed on later mounts until replayed", () => {
    window.localStorage.setItem("pc.seen.welcome", "1");
    const { rerender } = render(<SlateDeck id="welcome" replayToken={0} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    rerender(<SlateDeck id="welcome" replayToken={1} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
