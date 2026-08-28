import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSSE } from "@/hooks/useSSE";

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
});
