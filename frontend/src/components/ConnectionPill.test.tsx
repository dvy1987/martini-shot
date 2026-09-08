import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ConnectionPill from "@/components/ConnectionPill";

describe("ConnectionPill", () => {
  it("shows a checking state while the health request is pending", () => {
    render(
      <ConnectionPill
        connected={false}
        checking
        streamEnabled={false}
        sseStatus="unreachable"
      />,
    );

    expect(screen.getByText("Checking…")).toHaveAttribute(
      "title",
      "Checking the Martini Shot API",
    );
  });

  it("shows the API as live before a project event stream starts", () => {
    render(
      <ConnectionPill
        connected
        checking={false}
        streamEnabled={false}
        sseStatus="unreachable"
      />,
    );

    expect(screen.getByText("Live")).toHaveAttribute(
      "title",
      "The Martini Shot API is reachable",
    );
  });

  it("distinguishes a reconnecting event stream from an offline API", () => {
    const { rerender } = render(
      <ConnectionPill
        connected
        checking={false}
        streamEnabled
        sseStatus="reconnecting"
      />,
    );

    expect(screen.getByText("Reconnecting…")).toHaveAttribute(
      "title",
      "The API is reachable; reconnecting to the project event stream",
    );

    rerender(
      <ConnectionPill
        connected={false}
        checking={false}
        streamEnabled
        sseStatus="unreachable"
      />,
    );

    expect(screen.getByText("Offline")).toHaveAttribute(
      "title",
      "The Martini Shot API health check failed",
    );
  });
});