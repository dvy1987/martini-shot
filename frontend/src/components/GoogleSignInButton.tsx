/**
 * Owner sign-in (Google Identity Services). The settings controls decide
 * what the AUTONOMOUS loop may do, so changing them requires proving you
 * are the owner — the backend verifies the Google ID token against the
 * owner allowlist before any settings write lands.
 *
 * If no client id is configured the button renders its honest empty state
 * (owner sign-in unavailable) — it never fakes a signed-in state.
 */

import { useEffect, useRef, useState } from "react";
import { setGoogleIdToken } from "@/api/client";

const GIS_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

interface GoogleCredentialResponse {
  credential?: string;
}

interface GoogleIdApi {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: GoogleCredentialResponse) => void;
      }) => void;
      renderButton: (
        parent: HTMLElement,
        options: { theme: string; size: string; text: string; shape: string },
      ) => void;
    };
  };
}

function getGoogleIdApi(): GoogleIdApi | null {
  const g = window as unknown as { google?: GoogleIdApi };
  return g.google ?? null;
}

function loadGisScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (getGoogleIdApi()) {
      resolve();
      return;
    }
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${GIS_SCRIPT_SRC}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("GIS load failed")));
      return;
    }
    const script = document.createElement("script");
    script.src = GIS_SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("GIS load failed"));
    document.head.appendChild(script);
  });
}

interface GoogleSignInButtonProps {
  /** OAuth client id (build-time env; empty = gate unavailable). */
  clientId?: string;
  onSignedIn?: () => void;
}

export default function GoogleSignInButton({
  clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "",
  onSignedIn,
}: GoogleSignInButtonProps) {
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!clientId || signedIn) return;
    let cancelled = false;
    loadGisScript()
      .then(() => {
        if (cancelled) return;
        const api = getGoogleIdApi();
        if (!api || !buttonRef.current) return;
        api.accounts.id.initialize({
          client_id: clientId,
          callback: (response: GoogleCredentialResponse) => {
            if (!response.credential) {
              setError("Sign-in returned no credential");
              return;
            }
            setGoogleIdToken(response.credential);
            setSignedIn(true);
            onSignedIn?.();
          },
        });
        api.accounts.id.renderButton(buttonRef.current, {
          theme: "outline",
          size: "medium",
          text: "signin_with",
          shape: "pill",
        });
      })
      .catch(() => {
        if (!cancelled) setError("Could not load Google sign-in");
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, signedIn, onSignedIn]);

  if (!clientId) {
    return (
      <span className="font-mono text-xs text-ink-muted">
        Owner sign-in unavailable (no client id configured)
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span ref={buttonRef} aria-label="Sign in with Google" />
      {signedIn ? (
        <span className="font-mono text-xs text-ink-muted">owner signed in</span>
      ) : null}
      {error ? <span className="font-mono text-xs text-ink-muted">{error}</span> : null}
    </span>
  );
}
