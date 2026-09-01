import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";

import { listApprovals } from "@/api/endpoints";
import BeforeAfterWipe from "@/components/BeforeAfterWipe";
import CaseNote from "@/components/CaseNote";
import EmptyState from "@/components/EmptyState";
import { useApproveMutation, useRejectMutation } from "@/hooks/useApprovalMutations";
import { canDecide, spendSlate } from "@/lib/approvals";
import { asApiError } from "@/lib/errors";
import { cost } from "@/lib/formatters";
import { staggerChild, staggerParent } from "@/lib/motion";
import type { Approval, BackendReach } from "@/types/api";

interface ApprovalsRouteProps {
  backend: BackendReach;
}

function ApprovalCard({ item }: { item: Approval }) {
  const approve = useApproveMutation(item.approval_id);
  const reject = useRejectMutation(item.approval_id);
  const pending = approve.isPending || reject.isPending;
  const error = approve.error ?? reject.error;
  const showWipe = Boolean(item.before_url && item.after_url);
  const allow = canDecide(item.status);
  const slate = spendSlate(item.kind);

  return (
    <motion.article
      variants={staggerChild}
      className="rounded-md border border-line bg-surface-2 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg text-ink">{item.title}</h2>
          <p className="mt-1 font-mono text-xs uppercase tracking-widest text-ink-muted">
            {item.kind}
          </p>
          {slate ? (
            <p className="mt-2 font-mono text-xs uppercase tracking-widest text-danger">{slate}</p>
          ) : null}
        </div>
        <p className="font-mono text-sm tabular-nums text-tungsten">
          {item.cost_delta_micros != null ? cost(item.cost_delta_micros) : "—"}
        </p>
      </div>
      {item.detail ? <p className="mt-3 text-sm text-ink-muted">{item.detail}</p> : null}
      {showWipe && item.before_url && item.after_url ? (
        <BeforeAfterWipe beforeUrl={item.before_url} afterUrl={item.after_url} />
      ) : null}
      {error ? <div className="mt-3"><CaseNote error={asApiError(error)} /></div> : null}
      {allow ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={pending}
            onClick={() => approve.mutate()}
            className="rounded-sm border border-tungsten bg-tungsten px-3 py-2 font-mono text-xs uppercase tracking-wider text-bg transition-opacity ease-chrome hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            {approve.isPending ? "Approving…" : "Approve"}
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => reject.mutate()}
            className="rounded-sm border border-line bg-transparent px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink-muted transition-colors ease-chrome hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            {reject.isPending ? "Rejecting…" : "Reject"}
          </button>
        </div>
      ) : (
        <p className="mt-4 font-mono text-xs uppercase tracking-widest text-ink-muted">
          {item.status}
        </p>
      )}
    </motion.article>
  );
}

export default function ApprovalsRoute({ backend }: ApprovalsRouteProps) {
  const query = useQuery({
    queryKey: ["approvals"],
    queryFn: listApprovals,
    enabled: backend === "up",
  });

  if (backend === "checking") {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Checking the Screening Room…
      </p>
    );
  }

  if (backend === "down") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <EmptyState
          glyph="◎"
          title="Screening Room is dark"
          body="The backend is unreachable, so there is nothing honest to approve. No cards are invented."
        />
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <CaseNote error={asApiError(query.error)} onRetry={() => void query.refetch()} />
      </section>
    );
  }

  if (query.isPending) {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Loading queue…
      </p>
    );
  }

  const items = query.data ?? [];

  if (items.length === 0) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <EmptyState
          glyph="◎"
          title="No cards in the Screening Room"
          body="When a station proposes a change, it lands here with a real cost slate. Until then the queue stays empty."
        />
      </section>
    );
  }

  return (
    <motion.div
      variants={staggerParent}
      initial="hidden"
      animate="visible"
      className="mx-auto max-w-3xl space-y-4 px-6 py-8"
    >
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">Queue</p>
        <h1 className="mt-1 text-2xl text-ink">Screening Room</h1>
      </header>
      {items.map((item) => (
        <ApprovalCard key={item.approval_id} item={item} />
      ))}
    </motion.div>
  );
}
