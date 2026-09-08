/** Film-native status vocabulary — docs/design/DESIGN.md "Status vocabulary". */

import type { JobStatus } from "@/types/api";

export interface StatusMeta {
  term: string;
  hint: string;
  glyph: string;
  textClass: string;
}

/** Legend / Lens chip order — exception-first, then locked, then in-bin. */
export const STATUS_BOARD_ORDER: JobStatus[] = [
  "running",
  "needs_human",
  "fail",
  "quarantined",
  "throttled",
  "pass",
  "queued",
];

export const STATUS_META: Record<JobStatus, StatusMeta> = {
  queued: { term: "Waiting to start", hint: "This task is queued", glyph: "●", textClass: "text-ink-muted" },
  running: { term: "In progress", hint: "This task is running", glyph: "▶", textClass: "text-agent" },
  pass: { term: "Complete", hint: "This task passed", glyph: "◼", textClass: "text-signal" },
  fail: { term: "Failed", hint: "This task failed", glyph: "⚑", textClass: "text-danger" },
  quarantined: { term: "Set aside", hint: "This file was isolated", glyph: "◇", textClass: "text-tungsten" },
  needs_human: {
    term: "Needs review",
    hint: "A person needs to review this",
    glyph: "⚑",
    textClass: "text-tungsten",
  },
  throttled: {
    term: "Paused for budget",
    hint: "This task did not fit the available budget",
    glyph: "⏸",
    textClass: "text-tungsten",
  },
};

export function isJobStatus(value: string): value is JobStatus {
  return Object.hasOwn(STATUS_META, value);
}

/** Tolerant lookup for API strings that may not match the union. */
export function statusMetaFor(value: string): StatusMeta | null {
  return isJobStatus(value) ? STATUS_META[value] : null;
}

const UNKNOWN_META: StatusMeta = {
  term: "Unknown status",
  hint: "The system returned an unfamiliar status",
  glyph: "?",
  textClass: "text-ink-muted",
};

/** Total lookup for render paths: unknown API statuses render truthfully instead of crashing. */
export function statusMetaOrUnknown(value: string): StatusMeta {
  return isJobStatus(value)
    ? STATUS_META[value]
    : { ...UNKNOWN_META, hint: `${UNKNOWN_META.hint}: ${value}` };
}
