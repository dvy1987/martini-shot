import { useEffect, useRef } from "react";

import { progressStageIndex, PROGRESS_STAGES, type JourneyPhase } from "@/lib/journey";

interface ProgressRailProps {
  phase: JourneyPhase;
}

export default function ProgressRail({ phase }: ProgressRailProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);
  const currentIndex = progressStageIndex(phase);

  useEffect(() => {
    const scroller = scrollerRef.current;
    const active = activeRef.current;
    if (!scroller || !active) return;
    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const left = active.offsetLeft - (scroller.clientWidth - active.offsetWidth) / 2;
    const nextLeft = Math.max(0, left);
    if (typeof scroller.scrollTo === "function") {
      scroller.scrollTo({
        left: nextLeft,
        behavior: reduceMotion ? "auto" : "smooth",
      });
      return;
    }
    scroller.scrollLeft = nextLeft;
  }, [phase]);

  return (
    <div
      ref={scrollerRef}
      role="list"
      aria-label="Finishing stages"
      className="mt-4 flex gap-3 overflow-x-auto pb-2"
    >
      {PROGRESS_STAGES.map((stage) => {
        const phaseIndex = PROGRESS_STAGES.findIndex((item) => item.phase === stage.phase);
        const active = phase === stage.phase;
        const complete = currentIndex > phaseIndex;
        return (
          <div
            key={stage.phase}
            ref={active ? activeRef : undefined}
            role="listitem"
            data-stage={stage.phase}
            aria-current={active ? "step" : undefined}
            className={`w-44 shrink-0 border-t-2 pt-2 ${
              active ? "border-tungsten text-ink" : complete ? "border-signal text-ink-muted" : "border-line text-ink-muted"
            }`}
          >
            <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
              <span>{stage.name}</span>
              {active ? (
                <span
                  aria-label="Stage in progress"
                  className="inline-block size-2.5 animate-spin rounded-full border-2 border-tungsten border-t-transparent"
                />
              ) : null}
            </p>
            <p className="mt-1 text-xs font-sans normal-case tracking-normal leading-relaxed">
              {stage.description}
            </p>
          </div>
        );
      })}
    </div>
  );
}
