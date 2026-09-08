import { useState } from "react";

import { proposeCoverage as proposeCoverageApi } from "@/api/endpoints";
import type { ShotRow } from "@/types/api";

const ANGLES = [
  { id: "reverse_angle", label: "Reverse" },
  { id: "close_up", label: "Close-up" },
  { id: "wide_establishing", label: "Wide establishing" },
  { id: "over_the_shoulder", label: "Over the shoulder" },
  { id: "insert", label: "Insert" },
] as const;

interface CoverageControlsProps {
  shot: ShotRow;
  propose?: typeof proposeCoverageApi;
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

export default function CoverageControls({
  shot,
  propose = proposeCoverageApi,
}: CoverageControlsProps) {
  const [angle, setAngle] = useState("close_up");
  const [intent, setIntent] = useState("Same people, new angle");
  const sourceUri = defaultSourceUri(shot);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [proposedId, setProposedId] = useState<string | null>(null);

  if (shot.locked) {
    return (
      <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-signal">
        This clip is locked. Unlock it before creating an alternate angle.
      </p>
    );
  }

  async function submit() {
    setPending(true);
    setError(null);
    try {
      const result = await propose(shot.shot_id, {
        source_uri: sourceUri,
        angle,
        intent,
        reference_uris: [sourceUri],
        reason: "Looker-named coverage; clip is the subject reference",
      });
      setProposedId(result.approval_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Coverage proposal failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="mt-3 space-y-2 rounded-md border border-dashed border-line p-3"
      aria-label="Coverage"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <p className="font-mono text-[11px] uppercase tracking-widest text-ink-muted">
        Create another angle
      </p>
      <p className="text-xs text-ink-muted">
        Create another view of the same moment. Martini Shot will use this clip to keep the people and setting consistent.
      </p>
      <label className="grid gap-1 text-xs text-ink-muted">
        Camera angle
        <select
          value={angle}
          onChange={(event) => setAngle(event.target.value)}
          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-sans text-sm text-ink"
        >
          {ANGLES.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-xs text-ink-muted">
        What should the new view show?
        <input
          value={intent}
          onChange={(event) => setIntent(event.target.value)}
          required
          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-sans text-sm text-ink"
        />
      </label>
      <button
        type="submit"
        disabled={pending || !intent.trim() || !sourceUri.startsWith("gs://")}
        className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
      >
        {pending ? "Preparing suggestion…" : "Suggest another angle"}
      </button>
      {proposedId ? (
        <p className="font-mono text-[11px] text-tungsten">Suggestion created: {proposedId}</p>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
