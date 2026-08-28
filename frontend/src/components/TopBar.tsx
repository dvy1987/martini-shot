import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import ConnectionPill from "@/components/ConnectionPill";
import type { SseStatus } from "@/hooks/useSSE";
import { utcClock } from "@/lib/formatters";
import { ROUTES } from "@/lib/navigation";

interface TopBarProps {
  connected: boolean;
  sseStatus: SseStatus;
}

/** Charter top bar: brand, mono UTC clock, primary nav, ⌘K hint, connection pill. */
export default function TopBar({ connected, sseStatus }: TopBarProps) {
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
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3">
        <kbd
          title="Command palette lands with the Replit build steps"
          className="rounded border border-line px-1.5 py-0.5 font-mono text-xs text-ink-muted"
        >
          ⌘K
        </kbd>
        <ConnectionPill connected={connected} sseStatus={sseStatus} />
      </div>
    </header>
  );
}
