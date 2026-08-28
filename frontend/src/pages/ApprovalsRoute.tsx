import EmptyState from "@/components/EmptyState";

/**
 * Screening room / approvals inbox. Fix proposals and Spend Control escalations
 * (S5b) arrive as case files — before/after, cost delta, one decision.
 */
export default function ApprovalsRoute() {
  return (
    <section aria-labelledby="approvals-heading" className="mx-auto max-w-3xl px-6 py-10">
      <h1 id="approvals-heading" className="sr-only">
        Approvals
      </h1>
      <EmptyState
        glyph="⚖"
        title="No approvals waiting"
        body="When the agent proposes a fix or Spend Control asks for a spend decision, it appears here as a case file — before and after, cost delta, one decision."
      />
    </section>
  );
}
