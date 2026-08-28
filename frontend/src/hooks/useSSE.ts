/** SSE hook with exponential backoff + jitter (charter middleware policy). */

import { useEffect, useRef, useState } from "react";

export type SseStatus = "live" | "reconnecting" | "unreachable";

export interface SseState {
  status: SseStatus;
  lastEventAt: number | null;
}

const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 15_000;

export function useSSE(url: string | null): SseState {
  const [state, setState] = useState<SseState>({
    status: url ? "reconnecting" : "unreachable",
    lastEventAt: null,
  });
  const attemptRef = useRef(0);

  useEffect(() => {
    if (!url) {
      setState({ status: "unreachable", lastEventAt: null });
      return;
    }
    let source: EventSource | null = null;
    let timer: number | undefined;
    let disposed = false;

    const connect = () => {
      source = new EventSource(url);
      source.onopen = () => {
        attemptRef.current = 0;
        setState((previous) => ({ ...previous, status: "live" }));
      };
      source.onmessage = () => {
        setState((previous) => ({ ...previous, lastEventAt: Date.now() }));
      };
      source.onerror = () => {
        if (disposed) return;
        source?.close();
        setState((previous) => ({ ...previous, status: "reconnecting" }));
        const delay = Math.min(BASE_DELAY_MS * 2 ** attemptRef.current, MAX_DELAY_MS);
        const withJitter = delay * (0.75 + Math.random() * 0.5);
        attemptRef.current += 1;
        timer = window.setTimeout(connect, withJitter);
      };
    };
    connect();

    return () => {
      disposed = true;
      source?.close();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [url]);

  return state;
}
