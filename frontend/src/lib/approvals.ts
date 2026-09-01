import type { ApprovalKind, ApprovalStatus } from "@/types/api";

/** Charter Screening Room: Spend Control escalations wear this slate, not a generic badge. */
export const SPEND_SLATE = "PRODUCTION ACCOUNTING";

export function spendSlate(kind: ApprovalKind): string | null {
  return kind === "spend" ? SPEND_SLATE : null;
}

export function canDecide(status: ApprovalStatus): boolean {
  return status === "proposed";
}
