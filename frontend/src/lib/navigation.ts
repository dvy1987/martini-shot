/** Primary navigation model — kept out of component files so routes stay data. */

export type RouteId = "timeline" | "suggestions" | "approvals" | "analytics" | "reports";

export interface RouteEntry {
  id: RouteId;
  path: string;
  label: string;
}

export const ROUTES: RouteEntry[] = [
  { id: "timeline", path: "/", label: "Timeline" },
  { id: "suggestions", path: "/suggestions", label: "Suggestions" },
  { id: "approvals", path: "/approvals", label: "Approvals" },
  { id: "analytics", path: "/analytics", label: "Analytics" },
  { id: "reports", path: "/reports", label: "Reports" },
];
