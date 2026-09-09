/** Primary navigation model — kept out of component files so routes stay data.
 *
 * Unfinished screens (Studio on /changes, Reports on /reports) are not
 * offered here — owner demo ruling 2026-09-09 — but their routes stay
 * registered in App.tsx, so deep links keep working. Re-add an entry when
 * the screen ships.
 */

export type RouteId = "timeline" | "suggestions" | "decisions" | "analytics";

export interface RouteEntry {
  id: RouteId;
  path: string;
  label: string;
}

export const ROUTES: RouteEntry[] = [
  { id: "timeline", path: "/", label: "Central station" },
  { id: "suggestions", path: "/suggestions", label: "Suggestions" },
  { id: "decisions", path: "/decisions", label: "Decisions" },
  { id: "analytics", path: "/analytics", label: "Analytics" },
];
