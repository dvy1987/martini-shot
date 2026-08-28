import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSSE } from "@/hooks/useSSE";
import type { SseEvent } from "@/types/api";

/** Minimal scripted transport for jsdom (no EventSource there): open / error / close only. */
class ScriptedEventSource {
  static instances: ScriptedEventSource[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: unknown) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    ScriptedEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }
}

describe("useSSE", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    ScriptedEventSource.instances = [];
    vi.stubGlobal("EventSource", ScriptedEventSource);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("starts reconnecting and goes live when the stream opens", () => {
    const { result } = renderHook(() => useSSE("/api/v1/projects/p1/events"));
    expect(result.current.status).toBe("reconnecting");

    act(() => {
      ScriptedEventSource.instances[0]?.onopen?.();
    });
    expect(result.current.status).toBe("live");
  });

  it("closes and reconnects with backoff after an error", () => {
    const { result } = renderHook(() => useSSE("/api/v1/projects/p1/events"));
    const first = ScriptedEventSource.instances[0];

    act(() => {
      first?.onopen?.();
      first?.onerror?.();
    });
    expect(first?.closed).toBe(true);
    expect(result.current.status).toBe("reconnecting");

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(ScriptedEventSource.instances).toHaveLength(2);

    act(() => {
      ScriptedEventSource.instances[1]?.onopen?.();
    });
    expect(result.current.status).toBe("live");
  });

  it("reports unreachable without a url and never opens a stream", () => {
    const { result } = renderHook(() => useSSE(null));
    expect(result.current.status).toBe("unreachable");
    expect(ScriptedEventSource.instances).toHaveLength(0);
  });

  it("forwards valid event envelopes to the callback", () => {
    const events: SseEvent[] = [];
    renderHook(() => useSSE("/api/v1/projects/p1/events", (event) => events.push(event)));

    act(() => {
      ScriptedEventSource.instances[0]?.onmessage?.({
        data: JSON.stringify({
          type: "job.updated",
          payload: {
            job: {
              job_id: "job-1",
              station: "ingest",
              project_id: "p1",
              input_refs: [],
              status: "running",
              attempts: 1,
            },
          },
          at: "2026-08-28T00:00:00Z",
        }),
      });
    });

    expect(events).toHaveLength(1);
    expect(events[0]?.type).toBe("job.updated");
  });
});
