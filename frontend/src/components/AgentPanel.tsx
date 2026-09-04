import { cost } from "@/lib/formatters";
import type { Deliberation } from "@/types/api";

/**
 * H-1f agent panel: renders a real pc-deliberations record — which
 * specialists were consulted, what the verifier rejected, the ranked
 * actions, and any dissent between agents. Nothing here is invented;
 * when the record is empty the panel says so.
 */
export default function AgentPanel({ deliberation }: { deliberation: Deliberation }) {
  const ranked = deliberation.recommendation.ranked_actions ?? [];
  const dissent = deliberation.recommendation.dissent ?? [];
  const rejected = deliberation.verdict.rejected ?? [];
  const approved = deliberation.verdict.approved_specialists ?? [];

  return (
    <section aria-label="Agent deliberation">
      <h3 className="font-mono text-xs uppercase tracking-widest text-ink-muted">
        Agent deliberation
      </h3>

      <div className="mt-2 rounded-md border border-line bg-surface-2 p-4">
        <p className="font-mono text-xs uppercase tracking-wider text-ink-muted">
          {deliberation.specialists.length} specialists consulted
        </p>
        <ul className="mt-2 space-y-1">
          {deliberation.specialists.map((name) => (
            <li key={name} className="font-mono text-xs text-ink">
              <span aria-hidden className={approved.includes(name) ? "text-tungsten" : "text-ink-muted"}>
                {approved.includes(name) ? "✓" : "•"}
              </span>{" "}
              {name}
            </li>
          ))}
        </ul>
        {rejected.length > 0 ? (
          <div className="mt-3 border-t border-line pt-3">
            {rejected.map((entry) => (
              <p key={entry.claim_ref} className="mt-1 text-xs leading-relaxed text-danger">
                Rejected {entry.claim_ref}: {entry.reason}
              </p>
            ))}
          </div>
        ) : null}
      </div>

      <div className="mt-3 rounded-md border border-line bg-surface-2 p-4">
        <p className="font-mono text-xs uppercase tracking-wider text-ink-muted">
          Proposed next action
        </p>
        {ranked.length > 0 ? (
          <ul className="mt-2 space-y-2">
            {ranked.map((action, index) => (
              <li key={`${action.command_name}-${index}`} className="text-sm text-ink">
                <span className="font-mono text-xs">{action.command_name}</span>
                <span className="ml-2 font-mono text-xs text-tungsten">
                  {cost(action.cost_estimate_micros)}
                </span>
                <span className="ml-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
                  {action.reversible ? "reversible" : "irreversible"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-ink-muted">
            No ranked actions — the team proposed no change for this case.
          </p>
        )}
      </div>

      {dissent.length > 0 ? (
        <div className="mt-3 rounded-md border border-danger/40 bg-surface-2 p-4">
          <p className="font-mono text-xs uppercase tracking-wider text-danger">Dissent</p>
          {dissent.map((line, index) => (
            <p key={index} className="mt-2 text-sm leading-relaxed text-ink">
              {line}
            </p>
          ))}
        </div>
      ) : null}
    </section>
  );
}
