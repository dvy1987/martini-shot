import { useEffect, useRef } from "react";

import {
  progressStageTone,
  PROGRESS_STAGES,
  type JourneyPhase,
  type ProgressStageTone,
} from "@/lib/journey";
import type { Job, Worklist } from "@/types/api";

interface ProgressRailProps {
  phase: JourneyPhase;
  jobs?: readonly Job[];
  worklist?: Worklist | null;
}

const TONE_CARD: Record<ProgressStageTone, string> = {
  complete: "border-signal text-ink-muted",
  active: "border-tungsten text-ink",
  failed: "border-danger text-ink",
  pending: "border-line text-ink-muted",
};

const TONE_LABEL: Record<ProgressStageTone, string> = {
  complete: "Complete",
  active: "In progress",
  failed: "Failed",
  pending: "Not started",
};

export default function ProgressRail({
  phase,
  jobs = [],
  worklist = null,
}: ProgressRailProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);

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
  }, [phase, jobs, worklist]);

  return (
    <div
      ref={scrollerRef}
      role="list"
      aria-label="Finishing stages"
      className="mt-4 flex gap-3 overflow-x-auto pb-2"
    >
      {PROGRESS_STAGES.map((stage) => {
        const tone = progressStageTone(stage.phase, phase, jobs, worklist);
        const focused = tone === "active" || tone === "failed";
        return (
          <div
            key={stage.phase}
            ref={focused ? activeRef : undefined}
            role="listitem"
            data-stage={stage.phase}
            data-tone={tone}
            aria-current={focused ? "step" : undefined}
            aria-label={`${stage.name}, ${TONE_LABEL[tone]}`}
            className={`w-44 shrink-0 border-t-2 pt-2 ${TONE_CARD[tone]}`}
          >
            <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
              <span>{stage.name}</span>
              {tone === "active" ? (
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
