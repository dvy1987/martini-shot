import { motion } from "framer-motion";

import { fadeRise } from "@/lib/motion";

interface EmptyStateProps {
  glyph: string;
  title: string;
  body: string;
}

/** Designed empty state (charter: empty is a designed moment, never a blank screen). */
export default function EmptyState({ glyph, title, body }: EmptyStateProps) {
  return (
    <motion.div
      variants={fadeRise}
      initial="hidden"
      animate="visible"
      className="mx-auto mt-16 max-w-md rounded-xl border border-line bg-surface-1 p-8 text-center"
    >
      <div aria-hidden className="font-mono text-2xl text-ink-muted">
        {glyph}
      </div>
      <h2 className="mt-3 text-lg font-medium text-ink">{title}</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">{body}</p>
    </motion.div>
  );
}
