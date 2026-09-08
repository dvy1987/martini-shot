import { useState } from "react";

import { proposeRelight as proposeRelightApi } from "@/api/endpoints";
import type { ShotRow } from "@/types/api";

const PRESETS = [
  { id: "practical_lamp", label: "Practical lamp" },
  { id: "ambient_daylight", label: "Ambient daylight" },
  { id: "overhead_ceiling", label: "Overhead ceiling" },
  { id: "noir", label: "Noir" },
] as const;

interface RelightControlsProps {
  shot: ShotRow;
  propose?: typeof proposeRelightApi;
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

export default function RelightControls({
  shot,
  propose = proposeRelightApi,
}: RelightControlsProps) {
  const [preset, setPreset] = useState<string>("practical_lamp");
  const [sourceUri, setSourceUri] = useState(defaultSourceUri(shot));
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [proposedId, setProposedId] = useState<string | null>(null);

  if (shot.locked) {
    return (
      <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-signal">
        This clip is locked. Unlock it before creating a relit version.
      </p>
    );
  }

  async function submit() {
    setPending(true);
    setError(null);
    try {
      const result = await propose(shot.shot_id, {
        source_uri: sourceUri,
        preset,
        reason: `Looker-named or operator-picked ${preset}`,
      });
      setProposedId(result.approval_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Relight proposal failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="mt-3 space-y-2 rounded-md border border-dashed border-line p-3"
      aria-label="Relight"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <p className="font-mono text-[11px] uppercase tracking-widest text-ink-muted">
        Improve the lighting
      </p>
      <p className="text-xs text-ink-muted">
        Choose the lighting style you want to try.
      </p>
      <fieldset className="grid gap-1">
        <legend className="text-xs text-ink-muted">Lighting style</legend>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((item) => (
            <label
              key={item.id}
              className={`cursor-pointer rounded-sm border px-2 py-1 font-mono text-[11px] uppercase tracking-wider ${
                preset === item.id
                  ? "border-tungsten text-tungsten"
                  : "border-line text-ink hover:border-ink-muted"
              }`}
            >
              <input
                type="radio"
                name={`relight-preset-${shot.shot_id}`}
                value={item.id}
                checked={preset === item.id}
                onChange={() => setPreset(item.id)}
                className="sr-only"
              />
              {item.label}
            </label>
          ))}
        </div>
      </fieldset>
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
        disabled={pending || !sourceUri.startsWith("gs://")}
        className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
      >
        {pending ? "Preparing suggestion…" : "Suggest a lighting change"}
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
