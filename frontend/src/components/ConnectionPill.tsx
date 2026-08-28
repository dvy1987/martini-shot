import type { SseStatus } from "@/hooks/useSSE";

interface ConnectionPillProps {
  connected: boolean;
  sseStatus: SseStatus;
}

const LABEL: Record<SseStatus, string> = {
  live: "Live",
  reconnecting: "Reconnecting…",
  unreachable: "Offline",
};

/** Truthful reachability pill — the app never pretends the backend is there. */
export default function ConnectionPill({ connected, sseStatus }: ConnectionPillProps) {
  const label = connected ? LABEL[sseStatus] : "Offline";
  const tone = !connected
    ? "border-line text-ink-muted"
    : sseStatus === "live"
      ? "border-signal/40 text-signal"
      : "border-tungsten/40 text-tungsten";
  const dot = !connected ? "bg-ink-muted" : sseStatus === "live" ? "bg-signal" : "bg-tungsten";

  return (
    <span
      title={
        connected
          ? "Streaming project events over SSE"
          : "VITE_API_BASE_URL is not set — the board fills in when the backend connects"
      }
      className={`inline-flex items-center gap-2 rounded-full border bg-surface-1 px-2.5 py-1 font-mono text-xs ${tone}`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  );
}
