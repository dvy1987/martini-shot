import { useState } from "react";

import { proposeCorrection } from "@/api/endpoints";
import type { ShotRow } from "@/types/api";

interface CorrectionsControlsProps {
  shot: ShotRow;
  propose?: typeof proposeCorrection;
}

function defaultSourceUri(shot: ShotRow): string {
  const current = shot.alternates.find(
    (alternate) => alternate.alternate_id === shot.current_alternate_id,
  );
  return (
    current?.artifact_ref ||
    shot.alternates.find((alternate) => alternate.artifact_ref)?.artifact_ref ||
    ""
  );
}

export default function CorrectionsControls({
  shot,
  propose = proposeCorrection,
}: CorrectionsControlsProps) {
  const [intent, setIntent] = useState("");
  const [protectedSubjects, setProtectedSubjects] = useState("lead actor");
  const [constraints, setConstraints] = useState("preserve framing");
  const [sourceUri, setSourceUri] = useState(defaultSourceUri(shot));
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [proposedId, setProposedId] = useState<string | null>(null);
  const [rationale, setRationale] = useState<string | null>(null);

  if (shot.locked) {
    return (
      <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-signal">
        This clip is locked. Unlock it before creating a corrected version.
      </p>
    );
  }

  async function submit() {
    setPending(true);
    setError(null);
    try {
      const result = await propose(shot.shot_id, {
        source_uri: sourceUri,
        intent,
        protected_subjects: protectedSubjects
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        continuity_constraints: constraints
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      });
      setProposedId(result.approval_id);
      setRationale(result.agent?.rationale ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Correction proposal failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="mt-3 space-y-2 rounded-md border border-dashed border-line p-3"
      aria-label="Fix something in this clip"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <p className="font-mono text-[11px] uppercase tracking-widest text-ink-muted">
        Fix something in this clip
      </p>
      <label className="grid gap-1 text-xs text-ink-muted">
        What should change?
        <input
          value={intent}
          onChange={(event) => setIntent(event.target.value)}
          required
          placeholder="Replace the café sign text with OPEN"
          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-sans text-sm text-ink"
        />
      </label>
      <label className="grid gap-1 text-xs text-ink-muted">
        What must stay the same?
        <input
          value={protectedSubjects}
          onChange={(event) => setProtectedSubjects(event.target.value)}
          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-sans text-sm text-ink"
        />
      </label>
      <label className="grid gap-1 text-xs text-ink-muted">
        Other instructions
        <input
          value={constraints}
          onChange={(event) => setConstraints(event.target.value)}
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
      <button
        type="submit"
        disabled={pending || !intent.trim() || !sourceUri.startsWith("gs://")}
        className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
      >
        {pending ? "Preparing suggestion…" : "Suggest a correction"}
      </button>
      {proposedId ? (
        <p className="font-mono text-[11px] text-tungsten">
          Suggestion created: {proposedId}
        </p>
      ) : null}
      {rationale ? <p className="text-sm text-ink-muted">{rationale}</p> : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}