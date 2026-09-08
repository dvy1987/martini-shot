import type { SseStatus } from "@/hooks/useSSE";

interface ConnectionPillProps {
  connected: boolean;
  checking: boolean;
  streamEnabled: boolean;
  sseStatus: SseStatus;
}

const LABEL: Record<SseStatus, string> = {
  live: "Live",
  reconnecting: "Reconnecting…",
  unreachable: "Offline",
};

/** Truthful reachability pill — the app never pretends the backend is there. */
export default function ConnectionPill({
  connected,
  checking,
  streamEnabled,
  sseStatus,
}: ConnectionPillProps) {
  const label = checking
    ? "Checking…"
    : !connected
      ? "Offline"
      : !streamEnabled
        ? "Live"
        : LABEL[sseStatus];
  const isLive = connected && (!streamEnabled || sseStatus === "live");
  const tone = checking || !connected
    ? "border-line text-ink-muted"
    : isLive
      ? "border-signal/40 text-signal"
      : "border-tungsten/40 text-tungsten";
  const dot = checking || !connected ? "bg-ink-muted" : isLive ? "bg-signal" : "bg-tungsten";

  const title = checking
    ? "Checking the Martini Shot API"
    : !connected
      ? "The Martini Shot API health check failed"
      : !streamEnabled
        ? "The Martini Shot API is reachable"
        : sseStatus === "live"
          ? "Streaming project events over SSE"
          : "The API is reachable; reconnecting to the project event stream";

  return (
    <span
      title={title}
      className={`inline-flex items-center gap-2 rounded-full border bg-surface-1 px-2.5 py-1 font-mono text-xs ${tone}`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  );
}
