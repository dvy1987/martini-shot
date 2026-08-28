/**
 * Shared motion vocabulary — docs/design/DESIGN.md v3 "Motion system".
 * One damped spring for chrome + reveals; entrances ≤280ms; loops are sanctioned
 * separately. MotionConfig in main.tsx sets reducedMotion="user".
 */

import type { Transition, Variants } from "framer-motion";

/** THE spring — drawers, reveals, layout shifts (charter: ease-reveal equivalent). */
export const revealSpring: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 30,
  mass: 0.9,
};

/** Fast chrome micro-interaction (hover tint swaps, kbd presses). */
export const chromeTween: Transition = { duration: 0.12, ease: [0.4, 0, 0.6, 1] };

/** Side drawer / inspector: slides from the right, exits a touch faster. */
export const drawerVariants: Variants = {
  hidden: { x: "100%" },
  visible: { x: 0, transition: revealSpring },
  exit: { x: "100%", transition: { type: "spring", stiffness: 260, damping: 36 } },
};

/** Content blocks: fade + rise 8px, 280ms cap. */
export const fadeRise: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.28, ease: [0.16, 1, 0.3, 1] } },
  exit: { opacity: 0, y: -4, transition: { duration: 0.16, ease: chromeTween.ease } },
};

/** Staggered lists (timeline lanes, card grids) — parent orchestrates, children fadeRise. */
export const staggerParent: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
};

export const staggerChild: Variants = fadeRise;
