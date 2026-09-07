"""H-0b budgeted autonomy loop — dispatch mechanics (plan 2026-09-02).

The deliberation loop is a CALLER of H-0, not a second brain: candidates flow
through the same ApprovalStateMachine, self-approved as
`system:supervisor_budget` (the one new concept: the deliberation itself is
the approval decision, made under a pre-authorized budget).

Owner rulings baked in here:
- The nightly envelope (default $20) is the SOLE quantity bound — no
  action-count cap; reversibility + the dollar bound are the risk model.
- Envelope window: one envelope per calendar night (UTC), shared across all
  cycles that night.
- The daily house cap (Spend Control) sits ABOVE the envelope: a candidate
  that would breach it is refused even with envelope room left.
- Human-wins: once a human has decided on a target tonight, the loop's own
  ranking cannot re-fight it (same order-safety spirit as the sweeper).
- The autonomy toggle demotes the whole loop to propose-only: the ranked
  table is recorded for the morning report, nothing is dispatched.
- Adversarial money (C-7 discipline): a candidate with a garbage/negative
  cost estimate is not dispatchable (reuses spend.detect.coerce_cost_micros).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend.approvals.machine import propose_approval
from backend.jobs.models import utc_now_iso
from backend.stations.spend.detect import coerce_cost_micros, project_spend_micros
from backend.stations.spend.policy import project_budgets

log = logging.getLogger("pc.budget")

SUPERVISOR_APPROVER = "system:supervisor_budget"
CONTROL = "pc-control"
SETTINGS_DOC = "settings"
ACT_GATE_DOC = "act-gate"
# Bump when the ACT-gate eval contract hardens: a receipt from an older
# gate version never unlocks spending (fail closed).
ACT_GATE_VERSION = 1
ACT_GATE_SUITE = "deliberation_ranking_quality"
DEFAULT_ENVELOPE_MICROS = 20_000_000
VALID_AUTONOMY_MODES = ("propose_only", "act")

PROPOSE_ONLY = "propose_only"

# Nightly-envelope reservation ledger (review round 2, finding 3): one doc
# per UTC night; every dispatch reserves its cost inside a Firestore
# transaction so concurrent cycles can never both pass the same check and
# double-spend the envelope.
RESERVATION_COL = "pc-budget-reservations"
DAILY_RESERVATION_COL = "pc-daily-budget-reservations"


class _EnvelopeExceeded(Exception):
    """Raised inside the reservation transaction to refuse the write."""


def _night_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).date().isoformat()


def reserve_envelope(
    store: Any,
    *,
    cost: int,
    envelope: int,
    base_spent: int,
    collection: str = RESERVATION_COL,
    now: datetime | None = None,
) -> bool:
    """Atomically reserve `cost` against the nightly envelope. Returns False
    (writing nothing) when the reservation would exceed it. `base_spent` is
    the caller's pre-cycle snapshot of completed supervisor spend; the ledger
    carries every active reservation, and the compare-and-set inside the
    Firestore transaction is what makes concurrent cycles safe."""
    now = now or datetime.now(timezone.utc)
    night = _night_key(now)

    def mutate(doc: dict[str, Any]) -> dict[str, Any]:
        reserved = int(doc.get("reserved_micros") or 0)
        if base_spent + reserved + cost > envelope:
            raise _EnvelopeExceeded
        return {
            "night": night,
            "reserved_micros": reserved + cost,
            "updated_at": utc_now_iso(),
        }

    try:
        store.transactional_update(collection, night, mutate)
        return True
    except _EnvelopeExceeded:
        return False


def _daily_reservation_id(project_id: str, now: datetime) -> str:
    return f"{project_id}:{_night_key(now)}"


def reserve_daily_cap(
    store: Any,
    *,
    project_id: str,
    cost: int,
    daily_cap: int,
    base_spent: int,
    collection: str = DAILY_RESERVATION_COL,
    now: datetime | None = None,
) -> bool:
    """Atomically admit a cost against the project's daily house cap.

    Completed project spend is the immutable baseline for this admission;
    in-flight autonomy work is represented by the transactional reservation
    ledger. This closes the race between concurrent budgeted cycles.
    """
    now = now or datetime.now(timezone.utc)
    reservation_id = _daily_reservation_id(project_id, now)

    def mutate(doc: dict[str, Any]) -> dict[str, Any]:
        reserved = int(doc.get("reserved_micros") or 0)
        if base_spent + reserved + cost > daily_cap:
            raise _EnvelopeExceeded
        return {
            "project_id": project_id,
            "day": _night_key(now),
            "reserved_micros": reserved + cost,
            "updated_at": utc_now_iso(),
        }

    try:
        store.transactional_update(collection, reservation_id, mutate)
        return True
    except _EnvelopeExceeded:
        return False


def reconcile_daily_cap_reservation(
    store: Any,
    *,
    project_id: str,
    delta: int,
    collection: str = DAILY_RESERVATION_COL,
    now: datetime | None = None,
) -> None:
    """Refund or book the difference between a daily reservation and cost."""
    now = now or datetime.now(timezone.utc)
    reservation_id = _daily_reservation_id(project_id, now)

    def mutate(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "day": _night_key(now),
            "reserved_micros": max(0, int(doc.get("reserved_micros") or 0) + delta),
            "updated_at": utc_now_iso(),
        }

    store.transactional_update(collection, reservation_id, mutate)


def reconcile_reservation(
    store: Any,
    *,
    delta: int,
    collection: str = RESERVATION_COL,
    now: datetime | None = None,
) -> None:
    """Adjust the night ledger after dispatch: refund an over-estimate (or
    book an overrun) so the night tracks REAL spend, never the loop's guess.
    Clamped at zero — the ledger can only ever over-count, which fails safe
    (under-spends, never over-spends the envelope)."""
    now = now or datetime.now(timezone.utc)
    night = _night_key(now)

    def mutate(doc: dict[str, Any]) -> dict[str, Any]:
        reserved = max(0, int(doc.get("reserved_micros") or 0) + delta)
        return {
            "night": night,
            "reserved_micros": reserved,
            "updated_at": utc_now_iso(),
        }

    store.transactional_update(collection, night, mutate)


def ledger_reserved_micros(
    store: Any,
    *,
    collection: str = RESERVATION_COL,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    doc = store.get_doc(collection, _night_key(now)) or {}
    return int(doc.get("reserved_micros") or 0)


def act_gate_passed(store: Any, *, collection: str | None = None) -> bool:
    """Fail-closed ACT receipt check: a CURRENT-version, passing receipt for
    the ranking-quality suite must exist in `pc-control/act-gate`. Anything
    missing, stale, or malformed refuses ACT."""
    receipt = store.get_doc(collection or CONTROL, ACT_GATE_DOC) or {}
    try:
        version_ok = int(receipt.get("gate_version") or 0) == ACT_GATE_VERSION
    except (TypeError, ValueError):
        return False
    return (
        receipt.get("passed") is True
        and version_ok
        and str(receipt.get("suite") or "") == ACT_GATE_SUITE
    )


def load_autonomy_mode(
    store: Any, *, collection: str | None = None, doc_id: str = SETTINGS_DOC
) -> str:
    """The autonomy toggle from Firestore (`pc-control/settings`) — one flip
    demotes the whole loop to propose-only, no redeploy. Missing/invalid
    falls back to propose-only (safe default)."""
    raw = (store.get_doc(collection or CONTROL, doc_id) or {}).get("autonomy")
    mode = str(raw or "").strip().lower()
    return mode if mode in VALID_AUTONOMY_MODES else PROPOSE_ONLY


def load_envelope_micros(
    store: Any, *, collection: str | None = None, doc_id: str = SETTINGS_DOC
) -> int:
    """The envelope lives in Firestore (`pc-control/settings`) so the
    product's Settings UI can change it with no redeploy; missing/invalid
    falls back to the owner default."""
    raw = (store.get_doc(collection or CONTROL, doc_id) or {}).get(
        "post_command_budget_micros"
    )
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_ENVELOPE_MICROS
    return value if value > 0 else DEFAULT_ENVELOPE_MICROS


def _same_utc_day(stamp: str, now: datetime) -> bool:
    try:
        then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return then.astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date()


def supervisor_spend_micros(
    store: Any,
    approvals_col: str,
    jobs_col: str,
    *,
    now: datetime | None = None,
) -> int:
    """The supervisor's narrower counter: cost of actions the loop itself
    self-approved today (real job cost_micros when the completion hook wrote
    them, the loop's own estimate otherwise). Human- and Spend-Control spend
    is NOT counted here — it has its own accounting."""
    now = now or datetime.now(timezone.utc)
    total = 0
    for ap in store.list_where(approvals_col, "approver", SUPERVISOR_APPROVER):
        if not _same_utc_day(str(ap.get("decided_at") or ""), now):
            continue
        result = ap.get("result") or {}
        total += coerce_cost_micros(result.get("cost_micros")) or coerce_cost_micros(
            ap.get("budget_cost_micros")
        )
    return total


def _target_key(command_name: str, args: dict[str, Any]) -> str:
    return f"{command_name}:{json.dumps(args, sort_keys=True, default=str)}"


def _human_decided_targets(
    store: Any, approvals_col: str, project_id: str, *, now: datetime
) -> set[str]:
    """Targets a HUMAN decided on tonight — the loop yields to these for the
    rest of the night (human-wins rule)."""
    targets: set[str] = set()
    for ap in store.list_where(approvals_col, "project_id", project_id):
        approver = str(ap.get("approver") or "")
        if not approver or approver.startswith("system:"):
            continue
        if not _same_utc_day(str(ap.get("decided_at") or ""), now):
            continue
        command = ap.get("command") or {}
        targets.add(
            _target_key(str(command.get("name") or ""), dict(command.get("args") or {}))
        )
    return targets


def run_budgeted_dispatch(
    store: Any,
    machine: Any,
    ranked_actions: list[dict[str, Any]],
    *,
    project_id: str,
    approvals_col: str,
    jobs_col: str,
    policies: dict[str, Any] | None = None,
    autonomy_mode: str = "act",
    envelope_override: int | None = None,
    envelope_collection: str | None = None,
    gate_collection: str | None = None,
    annotator: Any | None = None,
    now: datetime | None = None,
    reservation_collection: str = RESERVATION_COL,
    daily_reservation_collection: str = DAILY_RESERVATION_COL,
    actionable: bool = True,
) -> dict[str, Any]:
    """Dispatch ranked candidates down the list through H-0 until the
    nightly envelope runs out. Returns the decision table; nothing is ever
    silently dropped (skips carry reasons and stay ranked).

    Concurrency (review round 2, finding 3): each dispatch reserves its cost
    inside a Firestore transaction on the night ledger
    (`reserve_envelope`) — two concurrent cycles can never both pass the
    same envelope check. After dispatch the reservation is reconciled to the
    actual cost, so the night tracks real spend.

    Defense in depth (review round 2, finding 8): a cycle that consulted a
    stand-in specialist (`actionable=False`) is demoted to propose-only even
    with a passing ACT receipt — stand-in findings never dispatch."""
    now = now or datetime.now(timezone.utc)
    envelope = (
        envelope_override
        if envelope_override is not None
        else load_envelope_micros(store, collection=envelope_collection)
    )
    decisions: list[dict[str, Any]] = []

    # Fail-closed activation (ACT-gate review fix 3): 'act' in settings alone
    # never unlocks spending — a current-version passing eval receipt must
    # exist. Without it the loop runs propose-only with a visible reason.
    if autonomy_mode == "act" and not act_gate_passed(
        store, collection=gate_collection
    ):
        autonomy_mode = PROPOSE_ONLY
        gate_reason = (
            f"act gate: no passing {ACT_GATE_SUITE} receipt "
            f"(version {ACT_GATE_VERSION} required)"
        )
    elif autonomy_mode == "act" and not actionable:
        autonomy_mode = PROPOSE_ONLY
        gate_reason = "stand-in specialist consulted — cycle not actionable"
    else:
        gate_reason = ""

    if autonomy_mode != "act":
        for row in ranked_actions:
            decisions.append(
                {
                    "command_name": row.get("command_name"),
                    "args": dict(row.get("args") or {}),
                    "cost_estimate_micros": coerce_cost_micros(
                        row.get("cost_estimate_micros")
                    ),
                    "decision": "skipped",
                    "reason": gate_reason or f"autonomy: {PROPOSE_ONLY}",
                    "ranked_for_morning_report": True,
                }
            )
        summary = {
            "mode": PROPOSE_ONLY,
            "decisions": decisions,
            "envelope_micros": envelope,
            "spent_micros": supervisor_spend_micros(
                store, approvals_col, jobs_col, now=now
            ),
        }
        _annotate_summary(annotator, summary)
        return summary

    spent = supervisor_spend_micros(store, approvals_col, jobs_col, now=now)
    base_spent = spent  # pre-cycle snapshot; the ledger carries this cycle
    house_spent = project_spend_micros(
        store.list_where(jobs_col, "project_id", project_id), now=now
    )
    daily_cap = project_budgets(policies or {}).get("daily_budget_micros", 0)
    humans = _human_decided_targets(store, approvals_col, project_id, now=now)

    for row in ranked_actions:
        name = str(row.get("command_name") or "")
        args = dict(row.get("args") or {})
        cost = coerce_cost_micros(row.get("cost_estimate_micros"))
        base = {
            "command_name": name,
            "args": args,
            "cost_estimate_micros": cost,
        }
        if cost <= 0:
            decisions.append(
                {**base, "decision": "skipped", "reason": "no credible cost estimate"}
            )
            continue
        if _target_key(name, args) in humans:
            decisions.append(
                {
                    **base,
                    "decision": "skipped",
                    "reason": "human already decided this target tonight",
                    "ranked_for_morning_report": True,
                }
            )
            continue
        if daily_cap > 0 and not reserve_daily_cap(
            store,
            project_id=project_id,
            cost=cost,
            daily_cap=daily_cap,
            base_spent=house_spent,
            collection=daily_reservation_collection,
            now=now,
        ):
            decisions.append(
                {
                    **base,
                    "decision": "skipped",
                    "reason": "daily house cap",
                    "ranked_for_morning_report": True,
                }
            )
            continue
        if not reserve_envelope(
            store,
            cost=cost,
            envelope=envelope,
            base_spent=base_spent,
            collection=reservation_collection,
            now=now,
        ):
            if daily_cap > 0:
                reconcile_daily_cap_reservation(
                    store,
                    project_id=project_id,
                    delta=-cost,
                    collection=daily_reservation_collection,
                    now=now,
                )
            decisions.append(
                {
                    **base,
                    "decision": "skipped",
                    "reason": "nightly envelope exhausted",
                    "ranked_for_morning_report": True,
                }
            )
            continue

        approval_id = propose_approval(
            store,
            {
                "project_id": project_id,
                "kind": "fix",
                "title": f"Budgeted autonomy: {name}",
                "detail": "evidence: "
                + ", ".join(str(ref) for ref in (row.get("evidence_refs") or [])),
                "command": {"name": name, "args": args},
                # The loop's own spend claim; reconciled to the real job
                # cost_micros once the completion hook writes them.
                "budget_cost_micros": cost,
            },
            collection=approvals_col,
        )
        merged = machine.dispatch(
            approval_id,
            "approve",
            approver=SUPERVISOR_APPROVER,
            reason="budgeted autonomy loop (H-0b)",
        )
        result = (merged or {}).get("result") or {}
        actual = coerce_cost_micros(result.get("cost_micros")) or cost
        # Reconcile the reservation to the real cost (refund an over-estimate,
        # book an overrun) — the night tracks actual spend, not the guess.
        reconcile_reservation(
            store,
            delta=actual - cost,
            collection=reservation_collection,
            now=now,
        )
        if daily_cap > 0:
            reconcile_daily_cap_reservation(
                store,
                project_id=project_id,
                delta=actual - cost,
                collection=daily_reservation_collection,
                now=now,
            )
        spent += actual
        house_spent += actual
        decisions.append(
            {
                **base,
                "decision": "dispatched",
                "reason": str(merged.get("status") or "approved"),
                "approval_id": approval_id,
            }
        )

    summary = {
        "mode": "act",
        "decisions": decisions,
        "envelope_micros": envelope,
        "spent_micros": spent,
        "house_spent_micros": house_spent,
        "daily_cap_micros": daily_cap,
    }
    _annotate_summary(annotator, summary)
    return summary


def _annotate_summary(annotator: Any | None, summary: dict[str, Any]) -> None:
    """Grafana-visible ranked table (C-4.3): one line per decision with the
    reason — what a judge reads, not just 'the AI thought'."""
    if annotator is None:
        return
    lines = [
        f"budget loop mode={summary['mode']} envelope={summary['envelope_micros']} "
        f"spent={summary['spent_micros']}"
    ]
    for d in summary["decisions"]:
        lines.append(
            f"{d['command_name']} est={d['cost_estimate_micros']} "
            f"{d['decision']} ({d['reason']})"
        )
    try:
        annotator("\n".join(lines), ["martini-shot", "deliberation", "budget"])
    except Exception:
        log.exception("budget-loop annotation failed (decisions persisted)")


def record_budget_outcome(
    store: Any,
    record: dict[str, Any],
    summary: dict[str, Any],
    *,
    deliberation_col: str = "pc-deliberations",
) -> dict[str, Any]:
    """Persist the decision table onto the cycle doc — the morning report
    reads ranked leftovers from here; nothing silently dropped."""
    status = record.get("status")
    if any(d.get("decision") == "dispatched" for d in summary.get("decisions", [])):
        status = "acted"
    updated = {
        **record,
        "status": status,
        "budget": {
            k: summary[k]
            for k in ("mode", "decisions", "envelope_micros", "spent_micros")
            if k in summary
        },
        "updated_at": utc_now_iso(),
    }
    store.set_doc(deliberation_col, str(record["cycle_id"]), updated)
    return updated


async def run_budgeted_cycle(
    trigger: dict[str, Any],
    settings: Any,
    store: Any,
    machine: Any,
    *,
    project_id: str,
    jobs_col: str,
    approvals_col: str,
    deliberation_col: str = "pc-deliberations",
    policies: dict[str, Any] | None = None,
    autonomy_mode: str = "act",
    envelope_override: int | None = None,
    envelope_collection: str | None = None,
    gate_collection: str | None = None,
    specialists: Any | None = None,
    verifier: Any | None = None,
    annotator: Any | None = None,
    now: datetime | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """One full budgeted autonomy cycle (H-0b steps 1-6): the multi-agent
    deliberation collects + verifies + ranks (Amendment A9), then this
    dispatches the ranked table through H-0 under the nightly envelope and
    persists the decision table onto the cycle doc.

    FAIL-CLOSED about specialists (review fix): every routed name must map
    to a real persona — a production caller that omits one is a wiring bug,
    never a reason to consult a stand-in."""
    from backend.supervisor.case import route_specialists
    from backend.supervisor.deliberation import run_deliberation_cycle

    provided = specialists or {}
    missing = [name for name in route_specialists(trigger) if name not in provided]
    if missing:
        raise ValueError(
            f"production deliberation requires real specialists for {missing} "
            f"(no stand-ins — wire backend.supervisor.team.production_specialists)"
        )
    record = await run_deliberation_cycle(
        trigger,
        settings,
        store=store,
        jobs_collection=jobs_col,
        deliberation_col=deliberation_col,
        specialists=specialists,
        verifier=verifier,
        annotator=annotator,
        propose=False,
        cycle_id=cycle_id,
    )
    summary = run_budgeted_dispatch(
        store,
        machine,
        list((record.get("recommendation") or {}).get("ranked_actions") or []),
        project_id=project_id,
        approvals_col=approvals_col,
        jobs_col=jobs_col,
        policies=policies,
        autonomy_mode=autonomy_mode,
        envelope_override=envelope_override,
        envelope_collection=envelope_collection,
        gate_collection=gate_collection,
        annotator=annotator,
        now=now,
        actionable=bool(record.get("actionable", True)),
    )
    return record_budget_outcome(
        store, record, summary, deliberation_col=deliberation_col
    )
