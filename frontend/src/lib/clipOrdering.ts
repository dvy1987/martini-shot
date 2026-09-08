export function reorder<T>(items: readonly T[], index: number, delta: -1 | 1): T[] {
  const next = [...items];
  const target = index + delta;
  if (index < 0 || index >= next.length || target < 0 || target >= next.length) return next;
  const current = next[index];
  next[index] = next[target] as T;
  next[target] = current as T;
  return next;
}