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
      caption: "Each clip moves through a set of checks. The timeline shows what is happening and what needs attention.",
      term: "Season Timeline",
    },
    {
      caption: "Martini Shot watches the run and highlights problems that need your attention.",
      term: "Markers & approvals",
    },
    {
      caption: "Open the evidence behind a result instead of relying on a summary alone.",
      term: "Evidence philosophy",
    },
  ],
  investigation: [
    { caption: "See what happened and when it happened.", term: "Alert" },
    { caption: "Open the logs, metrics, and traces used to investigate the problem.", term: "Evidence chain" },
    { caption: "See the problem, its likely cause, and how serious it is.", term: "Verdict" },
    { caption: "Review suggested work, its cost, and whether you need to approve it.", term: "Proposed action" },
  ],
  accounting: [
    {
      caption: "If the budget is not enough, Martini Shot pauses lower-priority work instead of overspending.",
      term: "Why is my station paused?",
    },
    {
      caption: "Review work that needs a decision, then approve or reject it.",
      term: "Throttle / stop / approve",
    },
    {
      caption: "Each proposed task shows why it was suggested and what it will cost.",
      term: "PRODUCTION ACCOUNTING",
    },
  ],
  dailies: [
    { caption: "Review the latest results from each part of the workflow.", term: "Morning report" },
    { caption: "Open the evidence behind each result.", term: "Citations" },
    { caption: "See how much work ran and how much it cost.", term: "Cost and results" },
  ],
};
