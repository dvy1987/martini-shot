/** Educational slates — DESIGN.md v2. Storage keys are `pc.seen.<id>`. */

export const SLATE_IDS = ["welcome", "investigation", "accounting", "dailies"] as const;
export type SlateId = (typeof SLATE_IDS)[number];

export function slateStorageKey(id: SlateId): string {
  return `pc.seen.${id}`;
}

export function isSlateSeen(id: SlateId, storage: Pick<Storage, "getItem">): boolean {
  return storage.getItem(slateStorageKey(id)) === "1";
}

export function markSlateSeen(id: SlateId, storage: Pick<Storage, "setItem">): void {
  storage.setItem(slateStorageKey(id), "1");
}

export function clearSlateSeen(id: SlateId, storage: Pick<Storage, "removeItem">): void {
  storage.removeItem(slateStorageKey(id));
}

export function slateForRoute(path: string): SlateId {
  if (path.startsWith("/approvals")) return "accounting";
  if (path.startsWith("/reports")) return "dailies";
  return "welcome";
}

export interface SlateFrame {
  caption: string;
  term: string;
}

export const SLATE_FRAMES: Record<SlateId, SlateFrame[]> = {
  welcome: [
    {
      caption: "Stations are lanes. Jobs are clips. Faults are markers.",
      term: "Season Timeline",
    },
    {
      caption: "Your supervisor never sleeps — tungsten marks the exceptions.",
      term: "Markers & approvals",
    },
    {
      caption: "Every claim is clickable evidence, not a chat transcript.",
      term: "Evidence philosophy",
    },
  ],
  investigation: [
    { caption: "What fired, in plain language and a timestamp.", term: "Alert" },
    { caption: "The agent's real queries, folded until you ask.", term: "Evidence chain" },
    { caption: "One sentence: severity and cause.", term: "Verdict" },
    { caption: "A proposed action with a cost, waiting on you.", term: "Proposed action" },
  ],
  accounting: [
    {
      caption: "Spend Control can pause a station. That is a production decision.",
      term: "Why is my station paused?",
    },
    {
      caption: "Throttle, stop, or approve — the inbox names the human.",
      term: "Throttle / stop / approve",
    },
    {
      caption: "The slate on a spend card is governance, not decoration.",
      term: "PRODUCTION ACCOUNTING",
    },
  ],
  dailies: [
    { caption: "Overnight wrap: one row per station.", term: "Morning report" },
    { caption: "Each verdict cites evidence you can open.", term: "Citations" },
    { caption: "Cost accounting stays in mono, in micro-dollars.", term: "The day accounted for" },
  ],
};
