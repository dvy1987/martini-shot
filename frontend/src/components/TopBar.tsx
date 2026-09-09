import { type RefObject, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import ConnectionPill from "@/components/ConnectionPill";
import type { SseStatus } from "@/hooks/useSSE";
import { utcClock } from "@/lib/formatters";
import { ROUTES } from "@/lib/navigation";

interface TopBarProps {
  connected: boolean;
  checking: boolean;
  streamEnabled: boolean;
  sseStatus: SseStatus;
  proposedCount: number;
  onOpenPalette: () => void;
  onReplaySlate: () => void;
  paletteTriggerRef: RefObject<HTMLButtonElement>;
}

/** Main navigation with the product tour and backend connection status. */
export default function TopBar({
  connected,
  checking,
  streamEnabled,
  sseStatus,
  proposedCount,
  onOpenPalette,
  onReplaySlate,
  paletteTriggerRef,
}: TopBarProps) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-line bg-surface-1 px-6">
      <div className="flex items-baseline gap-3">
        <span className="font-semibold tracking-tight">MARTINI SHOT</span>
        <span className="font-mono text-xs text-ink-muted">{utcClock(now)} UTC</span>
      </div>

      <nav className="flex items-center gap-1" aria-label="Primary">
        {ROUTES.map((entry) => (
          <NavLink
            key={entry.id}
            to={entry.path}
            end={entry.path === "/"}
            className={({ isActive }) =>
              isActive
                ? "rounded-md bg-surface-2 px-3 py-1.5 text-sm text-ink"
                : "rounded-md px-3 py-1.5 text-sm text-ink-muted transition-colors ease-chrome hover:text-ink"
            }
          >
            {entry.label}
            {entry.id === "decisions" && proposedCount > 0 ? (
              <span className="ml-2 font-mono text-xs text-tungsten">{proposedCount}</span>
            ) : null}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3">
        <button
          type="button"
          aria-label="Replay the product tour"
          onClick={onReplaySlate}
          className="rounded-sm px-2 py-1 font-mono text-xs text-ink-muted transition-colors ease-chrome hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
        >
          ?
        </button>
        <button
          ref={paletteTriggerRef}
          type="button"
          aria-label="Open command palette"
          aria-keyshortcuts="Meta+K Control+K"
          onClick={onOpenPalette}
          className="rounded border border-line px-1.5 py-0.5 font-mono text-xs text-ink-muted transition-colors ease-chrome hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
        >
          ⌘K
        </button>
        <ConnectionPill
          connected={connected}
          checking={checking}
          streamEnabled={streamEnabled}
          sseStatus={sseStatus}
        />
      </div>
    </header>
  );
}
