/** Film-native status vocabulary — docs/design/DESIGN.md "Status vocabulary". */

import type { JobStatus } from "@/types/api";

export interface StatusMeta {
  term: string;
  hint: string;
  glyph: string;
  textClass: string;
}

export const STATUS_META: Record<JobStatus, StatusMeta> = {
  queued: { term: "In bin", hint: "queued", glyph: "●", textClass: "text-ink-muted" },
  running: { term: "In the lab", hint: "running", glyph: "▶", textClass: "text-agent" },
  pass: { term: "Locked", hint: "passed", glyph: "◼", textClass: "text-signal" },
  fail: { term: "Failed QC", hint: "failed", glyph: "⚑", textClass: "text-danger" },
  quarantined: { term: "Vaulted", hint: "quarantined", glyph: "◇", textClass: "text-tungsten" },
  needs_human: {
    term: "Flagged",
    hint: "needs human review",
    glyph: "⚑",
    textClass: "text-tungsten",
  },
  throttled: {
    term: "Held by accounting",
    hint: "throttled by Spend Control",
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
