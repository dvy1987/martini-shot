/** Primary navigation model — kept out of component files so routes stay data. */

export type RouteId = "timeline" | "changes" | "suggestions" | "decisions" | "analytics" | "reports";

export interface RouteEntry {
  id: RouteId;
  path: string;
  label: string;
}

export const ROUTES: RouteEntry[] = [
  { id: "timeline", path: "/", label: "Central station" },
  { id: "changes", path: "/changes", label: "Studio" },
  { id: "suggestions", path: "/suggestions", label: "Suggestions" },
  { id: "decisions", path: "/decisions", label: "Decisions" },
  { id: "analytics", path: "/analytics", label: "Analytics" },
  { id: "reports", path: "/reports", label: "Reports" },
];
