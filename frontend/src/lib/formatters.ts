/** Charter formatters: timecode, mono clock, micro-dollar costs, relative time. */

export function timecode(durationMs: number): string {
  const total = Math.max(0, Math.round(durationMs));
  const ms = total % 1000;
  const seconds = Math.floor(total / 1000) % 60;
  const minutes = Math.floor(total / 60_000) % 60;
  const hours = Math.floor(total / 3_600_000);
  const pad = (value: number, width = 2) => String(value).padStart(width, "0");
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}.${pad(ms, 3)}`;
}

export function utcClock(date: Date): string {
  return date.toISOString().slice(11, 19);
}

export function cost(micros: number): string {
  const dollars = micros / 1_000_000;
  const formatted =
    dollars > 0 && dollars < 1
      ? dollars.toFixed(4)
      : dollars.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `$${formatted}`;
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  const deltaMs = now.getTime() - then;
  if (Number.isNaN(deltaMs)) return "unknown";
  const seconds = Math.round(deltaMs / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
