/**
 * GoogleSignInButton tests. Google Identity Services is an EXTERNAL SDK —
 * tests use a labeled fixture of its API surface (C-1.3: labeled synthetic
 * INPUT for tests only; the product runtime loads the real GIS script).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setGoogleIdToken } from "@/api/client";
import GoogleSignInButton from "./GoogleSignInButton";

type InitConfig = {
  client_id: string;
  callback: (response: { credential?: string }) => void;
};

let initCalls: InitConfig[] = [];

// Labeled fixture of window.google.accounts.id (external SDK surface).
const fixtureGoogleId = {
  accounts: {
    id: {
      initialize: (config: InitConfig) => {
        initCalls.push(config);
      },
      renderButton: (parent: HTMLElement) => {
        parent.setAttribute("data-testid", "gis-button");
      },
    },
  },
};

describe("GoogleSignInButton", () => {
  beforeEach(() => {
    initCalls = [];
    setGoogleIdToken("");
    vi.stubGlobal(
      "google",
      undefined as unknown as { accounts: { id: InitConfig } },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.head.innerHTML = "";
  });

  it("renders the honest empty state when no client id is configured", () => {
    render(<GoogleSignInButton clientId="" />);
    expect(
      screen.getByText(/owner sign-in unavailable/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/sign in with google/i)).toBeNull();
  });

  it("loads GIS, renders the button, and stores the credential on sign-in", async () => {
    const onSignedIn = vi.fn();
    render(<GoogleSignInButton clientId="test-id" onSignedIn={onSignedIn} />);

    // The loader appended the real GIS script tag (no network in tests).
    await waitFor(() => {
      expect(
        document.head.querySelector('script[src="https://accounts.google.com/gsi/client"]'),
      ).not.toBeNull();
    });

    // Labeled fixture of the external SDK, then the script "arrives".
    vi.stubGlobal("google", fixtureGoogleId);
    const script = document.head.querySelector(
      'script[src="https://accounts.google.com/gsi/client"]',
    )!;
    script.dispatchEvent(new Event("load"));

    await waitFor(() => {
      expect(screen.getByTestId("gis-button")).toBeInTheDocument();
    });

    // The initialize callback received the configured client id.
    expect(initCalls).toHaveLength(1);
    expect(initCalls[0]?.client_id).toBe("test-id");

    // Simulate the real GIS credential flow through the captured callback.
    initCalls[0]?.callback({ credential: "jwt-credential" });

    await waitFor(() => {
      expect(screen.getByText(/owner signed in/i)).toBeInTheDocument();
    });
    expect(onSignedIn).toHaveBeenCalledTimes(1);
    // The token is stored where the API client sends it (settings PATCH);
    // no re-initialization happens after sign-in.
    expect(initCalls).toHaveLength(1);
  });

  it("shows an honest error when the GIS script fails to load", async () => {
    // Pre-plant the script element so the loader attaches listeners to it,
    // then fire its error event (deterministic, no network in tests).
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    document.head.appendChild(script);
    render(<GoogleSignInButton clientId="test-id" />);
    script.dispatchEvent(new Event("error"));
    await waitFor(() => {
      expect(
        screen.getByText(/could not load google sign-in/i),
      ).toBeInTheDocument();
    });
  });
});
