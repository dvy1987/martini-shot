/** Direction: film-lab ops console — match CorrectionsControls / DESIGN.md v3 */
import { useState } from "react";

import { proposeExtend as proposeExtendApi, proposeMaster as proposeMasterApi } from "@/api/endpoints";
import type { ShotRow } from "@/types/api";

interface ExtendControlsProps {
  shot: ShotRow;
  proposeExtend?: typeof proposeExtendApi;
  proposeMaster?: typeof proposeMasterApi;
}

const FLICKER_GATE = 0.02;

function defaultSourceUri(shot: ShotRow): string {
  const original = shot.alternates.find(
    (alternate) => alternate.artifact_ref && alternate.op !== "extend",
  );
  if (original?.artifact_ref) {
    return original.artifact_ref;
  }
  const current = shot.alternates.find(
    (alternate) => alternate.alternate_id === shot.current_alternate_id,
  );
  return (
    current?.artifact_ref ||
    shot.alternates.find((alternate) => alternate.artifact_ref)?.artifact_ref ||
    ""
  );
}

function hasPassingExtendDraft(shot: ShotRow): boolean {
  return shot.alternates.some((alternate) => {
    if (alternate.op !== "extend" || alternate.tier === "master") {
      return false;
    }
    const flicker = alternate.eval_scores?.flicker;
    return typeof flicker === "number" && flicker < FLICKER_GATE;
  });
}

export default function ExtendControls({
  shot,
  proposeExtend = proposeExtendApi,
  proposeMaster = proposeMasterApi,
}: ExtendControlsProps) {
  const [reason, setReason] = useState("Continue the action naturally");
  const [sourceUri, setSourceUri] = useState(defaultSourceUri(shot));
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<"extend" | "master" | null>(null);
  const [proposedId, setProposedId] = useState<string | null>(null);

  if (shot.locked) {
    return (
      <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-signal">
        This clip is locked. Unlock it before creating an extended version.
      </p>
    );
  }

  async function submitExtend() {
    setPending("extend");
    setError(null);
    try {
      const result = await proposeExtend(shot.shot_id, {
        source_uri: sourceUri,
        reason,
      });
      setProposedId(result.approval_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Extend proposal failed.");
    } finally {
      setPending(null);
    }
  }

  async function submitMaster() {
    setPending("master");
    setError(null);
    try {
      const result = await proposeMaster(shot.shot_id, {
        op: "extend",
        source_uri: sourceUri,
        reason: "Master after passing draft QC",
      });
      setProposedId(result.approval_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Master proposal failed.");
    } finally {
      setPending(null);
    }
  }

  const canSubmit = Boolean(pending) || !sourceUri.startsWith("gs://");

  return (
    <form
      className="mt-3 space-y-2 rounded-md border border-dashed border-line p-3"
      aria-label="Extend"
      onSubmit={(event) => {
        event.preventDefault();
        void submitExtend();
      }}
    >
      <p className="font-mono text-[11px] uppercase tracking-widest text-ink-muted">
        Continue this clip
      </p>
      <label className="grid gap-1 text-xs text-ink-muted">
        What should continue?
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Continue the action naturally"
          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-sans text-sm text-ink"
        />
      </label>
      <label className="grid gap-1 text-xs text-ink-muted">
        Video file
        <input
          value={sourceUri}
          onChange={(event) => setSourceUri(event.target.value)}
          required
          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-mono text-xs text-ink"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={canSubmit}
          className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
        >
          {pending === "extend" ? "Preparing suggestion…" : "Suggest an extension"}
        </button>
        {hasPassingExtendDraft(shot) ? (
          <button
            type="button"
            disabled={canSubmit}
            onClick={() => void submitMaster()}
            className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
          >
            {pending === "master" ? "Preparing final version…" : "Create final version"}
          </button>
        ) : null}
      </div>
      {proposedId ? (
        <p className="font-mono text-[11px] text-tungsten">
          Suggestion created: {proposedId}
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
