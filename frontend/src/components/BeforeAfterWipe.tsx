import { useId, useRef, useState } from "react";
import { motion } from "framer-motion";

import { chromeTween } from "@/lib/motion";
import { wipeFromClientX, wipeFromKey } from "@/lib/wipe";

interface BeforeAfterWipeProps {
  beforeUrl: string;
  afterUrl: string;
}

export default function BeforeAfterWipe({ beforeUrl, afterUrl }: BeforeAfterWipeProps) {
  const [percent, setPercent] = useState(50);
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const labelId = useId();

  function moveTo(clientX: number) {
    const box = trackRef.current?.getBoundingClientRect();
    if (!box) return;
    setPercent(wipeFromClientX(clientX, box.left, box.width));
  }

  return (
    <div className="mt-4">
      <p id={labelId} className="font-mono text-xs uppercase tracking-widest text-ink-muted">
        Before / after
      </p>
      <div
        ref={trackRef}
        className="relative mt-2 aspect-video cursor-ew-resize overflow-hidden rounded-md border border-line bg-surface-2"
        onPointerDown={(event) => {
          dragging.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          moveTo(event.clientX);
        }}
        onPointerMove={(event) => {
          if (dragging.current) moveTo(event.clientX);
        }}
        onPointerUp={() => {
          dragging.current = false;
        }}
        onPointerCancel={() => {
          dragging.current = false;
        }}
      >
        <img src={afterUrl} alt="After" className="absolute inset-0 size-full object-cover" />
        <img
          src={beforeUrl}
          alt="Before"
          className="absolute inset-0 size-full object-cover"
          style={{ clipPath: `inset(0 ${100 - percent}% 0 0)` }}
        />
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 w-px bg-tungsten"
          animate={{ left: `${percent}%` }}
          transition={chromeTween}
        />
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={percent}
        role="slider"
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
        className="mt-2 w-full accent-tungsten"
        onChange={(event) => setPercent(Number(event.target.value))}
        onKeyDown={(event) => {
          const next = wipeFromKey(percent, event.key);
          if (next !== percent) {
            event.preventDefault();
            setPercent(next);
          }
        }}
      />
    </div>
  );
}
