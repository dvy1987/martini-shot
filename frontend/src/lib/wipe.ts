/** Before/after wipe position — 0 = full before, 100 = full after. */

export function clampWipe(percent: number): number {
  if (!Number.isFinite(percent)) return 0;
  return Math.min(100, Math.max(0, percent));
}

export function wipeFromClientX(clientX: number, left: number, width: number): number {
  if (width <= 0) return 0;
  return clampWipe(((clientX - left) / width) * 100);
}

export function wipeFromKey(current: number, key: string, step = 5): number {
  if (key === "ArrowLeft" || key === "Home") {
    return key === "Home" ? 0 : clampWipe(current - step);
  }
  if (key === "ArrowRight" || key === "End") {
    return key === "End" ? 100 : clampWipe(current + step);
  }
  return current;
}
