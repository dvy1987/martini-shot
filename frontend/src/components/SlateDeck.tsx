import { useEffect, useId, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { fadeRise } from "@/lib/motion";
import {
  isSlateSeen,
  markSlateSeen,
  SLATE_FRAMES,
  type SlateId,
} from "@/lib/slates";

interface SlateDeckProps {
  id: SlateId;
  replayToken: number;
}

function SlateDiagram({ id, instant }: { id: SlateId; instant: boolean }) {
  const duration = instant ? 0 : 0.55;
  const delay = instant ? 0 : 0.12;

  return (
    <svg viewBox="0 0 320 96" className="h-24 w-full text-tungsten" aria-hidden>
      {id === "welcome" ? (
        <>
          <motion.path
            d="M24 24 H296"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            initial={{ pathLength: instant ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration }}
          />
          <motion.rect
            x="24"
            y="40"
            width="80"
            height="36"
            rx="4"
            fill="none"
            stroke="currentColor"
            initial={{ pathLength: instant ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration, delay }}
          />
          <motion.rect
            x="120"
            y="40"
            width="80"
            height="36"
            rx="4"
            fill="none"
            stroke="currentColor"
            initial={{ pathLength: instant ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration, delay: delay * 2 }}
          />
          <motion.rect
            x="216"
            y="40"
            width="80"
            height="36"
            rx="4"
            fill="none"
            stroke="currentColor"
            initial={{ pathLength: instant ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration, delay: delay * 3 }}
          />
        </>
      ) : null}
      {id === "investigation" ? (
        <>
          {[0, 1, 2, 3].map((slot) => (
            <motion.rect
              key={slot}
              x={24 + slot * 74}
              y="28"
              width="64"
              height="40"
              rx="4"
              fill="none"
              stroke="currentColor"
              initial={{ pathLength: instant ? 1 : 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration, delay: delay * slot }}
            />
          ))}
        </>
      ) : null}
      {id === "accounting" ? (
        <motion.path
          d="M40 48 H160 M160 32 V64 M200 48 H280"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          initial={{ pathLength: instant ? 1 : 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration }}
        />
      ) : null}
      {id === "dailies" ? (
        <>
          {[0, 1, 2].map((slot) => (
            <motion.rect
              key={slot}
              x={36 + slot * 90}
              y="24"
              width="72"
              height="48"
              rx="4"
              fill="none"
              stroke="currentColor"
              initial={{ pathLength: instant ? 1 : 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration, delay: delay * slot }}
            />
          ))}
        </>
      ) : null}
    </svg>
  );
}

export default function SlateDeck({ id, replayToken }: SlateDeckProps) {
  const frames = SLATE_FRAMES[id];
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const titleId = useId();

  useEffect(() => {
    setIndex(0);
    setOpen(!isSlateSeen(id, window.localStorage));
  }, [id]);

  useEffect(() => {
    if (replayToken === 0) return;
    setIndex(0);
    setOpen(true);
  }, [replayToken]);

  function dismiss() {
    markSlateSeen(id, window.localStorage);
    setOpen(false);
  }

  function next() {
    if (index >= frames.length - 1) {
      dismiss();
      return;
    }
    setIndex((current) => current + 1);
  }

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") dismiss();
      if (event.key === "ArrowRight") next();
      if (event.key === "ArrowLeft") setIndex((current) => Math.max(0, current - 1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const frame = frames[index];
  if (!frame) return null;

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="fixed inset-0 z-[60] grid place-items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
        >
          <button
            type="button"
            aria-label="Dismiss slate"
            className="absolute inset-0"
            style={{ backgroundColor: "var(--scrim)" }}
            onClick={dismiss}
          />
          <motion.div
            variants={fadeRise}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="relative z-10 w-[min(640px,calc(100%-2rem))] rounded-md border border-line bg-surface-2 p-6 shadow-[var(--shadow-lift)]"
          >
            <button
              type="button"
              onClick={dismiss}
              className="absolute right-4 top-4 font-mono text-xs uppercase tracking-wider text-ink-muted transition-colors ease-chrome hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              Skip
            </button>
            <SlateDiagram id={id} instant={Boolean(reduce)} />
            <p id={titleId} className="mt-4 text-lg text-ink">
              {frame.caption}
            </p>
            <p className="mt-1 font-mono text-xs uppercase tracking-widest text-ink-muted">
              {frame.term}
            </p>
            <div className="mt-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex gap-1" aria-hidden>
                  {frames.map((_, dot) => (
                    <span
                      key={dot}
                      className={`h-1.5 w-1.5 rounded-full ${dot === index ? "bg-tungsten" : "bg-line"}`}
                    />
                  ))}
                </div>
                <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">
                  ← → · Esc
                </p>
              </div>
              <button
                type="button"
                onClick={next}
                className="rounded-sm border border-line bg-surface-1 px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                {index >= frames.length - 1 ? "Close" : "Next →"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
