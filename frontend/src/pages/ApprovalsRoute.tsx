import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";

import { listApprovals, listDeliberations } from "@/api/endpoints";
import BeforeAfterWipe from "@/components/BeforeAfterWipe";
import CaseNote from "@/components/CaseNote";
import EmptyState from "@/components/EmptyState";
import { useApproveMutation, useRejectMutation } from "@/hooks/useApprovalMutations";
import { canDecide, spendSlate } from "@/lib/approvals";
import { dissentForJob } from "@/lib/deliberations";
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
  const deliberationQuery = useQuery({
    queryKey: ["deliberations", item.project_id, item.job_id ?? null],
    queryFn: () => listDeliberations(item.project_id, item.job_id),
    enabled: Boolean(item.job_id),
  });
  const dissent = item.job_id
    ? dissentForJob(deliberationQuery.data ?? [], item.job_id)
    : [];

  return (
    <motion.article
      variants={staggerChild}
      className="rounded-md border border-line bg-surface-2 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg text-ink">{item.title}</h2>
          <p className="mt-1 font-mono text-xs uppercase tracking-widest text-ink-muted">
            {item.kind.replaceAll("_", " ")}
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
      {dissent.length > 0 ? (
        <div className="mt-3 rounded-sm border border-danger/40 px-3 py-2">
          {dissent.map((line, index) => (
            <p key={index} className="text-xs leading-relaxed text-danger">
              The agents disagree: {line}
            </p>
          ))}
        </div>
      ) : null}
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
          {item.status.replaceAll("_", " ")}
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
        Checking for items that need your approval…
      </p>
    );
  }

  if (backend === "down") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <EmptyState
          glyph="◎"
          title="Approvals are unavailable"
          body="The service is unavailable, so approval items cannot be loaded."
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
        Loading approval requests…
      </p>
    );
  }

  const items = query.data ?? [];
  const actionable = items.filter((item) => canDecide(item.status));
  const history = items.filter((item) => !canDecide(item.status));

  if (items.length === 0) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <EmptyState
          glyph="◎"
          title="No approval requests"
          body="When Martini Shot needs you to approve a change, it will appear here with the reason and estimated cost."
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
          <p className={`font-mono text-xs uppercase tracking-widest ${actionable.length > 0 ? "text-tungsten" : "text-ink-muted"}`}>{actionable.length > 0 ? "Needs your decision" : "Approval history"}</p>
          <h1 className="mt-1 text-2xl text-ink">Approvals</h1>
          <p className="mt-2 max-w-xl text-sm text-ink-muted">{actionable.length > 0 ? "Review the reason and evidence, then approve or reject the work waiting for your decision." : "Nothing needs your decision right now. Previous decisions remain available below."}</p>
      </header>
      {actionable.map((item) => (
        <ApprovalCard key={item.approval_id} item={item} />
      ))}
      {history.length > 0 ? (
        <details className="border border-line bg-surface-1 p-4">
          <summary className="cursor-pointer font-mono text-xs uppercase tracking-widest text-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">
            Previous decisions · {history.length}
          </summary>
          <div className="mt-4 space-y-4">
            {history.map((item) => (
              <ApprovalCard key={item.approval_id} item={item} />
            ))}
          </div>
        </details>
      ) : null}
    </motion.div>
  );
}
