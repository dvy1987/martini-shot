import type { ApprovalKind, ApprovalStatus } from "@/types/api";

/** Budget-related decisions use a clear label in the UI. */
export const SPEND_SLATE = "Budget review";

export function spendSlate(kind: ApprovalKind): string | null {
  return kind === "spend" ? SPEND_SLATE : null;
}

export function canDecide(status: ApprovalStatus): boolean {
  return status === "proposed";
}
