import { useState } from "react";

import { proposeCameraLanguage as proposeCameraLanguageApi } from "@/api/endpoints";
import type { ShotRow } from "@/types/api";

const MOVEMENTS = [
  { id: "dolly_tracking", label: "Dolly / tracking" },
  { id: "dolly_zoom", label: "Dolly zoom" },
  { id: "handheld_shaky", label: "Handheld" },
  { id: "steadicam", label: "Steadicam" },
  { id: "whip_pan", label: "Whip pan" },
  { id: "crash_zoom", label: "Crash zoom" },
  { id: "snorricam", label: "SnorriCam" },
  { id: "locked_off", label: "Locked-off" },
] as const;

interface CameraLanguageControlsProps {
  shot: ShotRow;
  propose?: typeof proposeCameraLanguageApi;
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

export default function CameraLanguageControls({
  shot,
  propose = proposeCameraLanguageApi,
}: CameraLanguageControlsProps) {
  const [movement, setMovement] = useState("dolly_tracking");
  const sourceUri = defaultSourceUri(shot);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [proposedId, setProposedId] = useState<string | null>(null);

  if (shot.locked) {
    return (
      <p className="mt-3 font-mono text-[11px] uppercase tracking-wider text-signal">
        This clip is locked. Unlock it before creating a camera-movement version.
      </p>
    );
  }

  async function submit() {
    setPending(true);
    setError(null);
    try {
      const result = await propose(shot.shot_id, {
        source_uri: sourceUri,
        movement,
        reason: `Genre-aware suggestion: ${movement} (model-named)`,
      });
      setProposedId(result.approval_id);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Camera language proposal failed.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="mt-3 space-y-2 rounded-md border border-dashed border-line p-3"
      aria-label="Camera language"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <p className="font-mono text-[11px] uppercase tracking-widest text-ink-muted">
        Change the camera movement
      </p>
      <p className="text-xs text-ink-muted">
        Choose the camera movement you want to try.
      </p>
      <fieldset className="grid gap-1">
        <legend className="text-xs text-ink-muted">Camera movement</legend>
        <div className="flex flex-wrap gap-2">
          {MOVEMENTS.map((item) => (
            <label
              key={item.id}
              className={`cursor-pointer rounded-sm border px-2 py-1 font-mono text-[11px] uppercase tracking-wider ${
                movement === item.id
                  ? "border-tungsten text-tungsten"
                  : "border-line text-ink hover:border-ink-muted"
              }`}
            >
              <input
                type="radio"
                name={`camera-move-${shot.shot_id}`}
                value={item.id}
                checked={movement === item.id}
                onChange={() => setMovement(item.id)}
                className="sr-only"
              />
              {item.label}
            </label>
          ))}
        </div>
      </fieldset>
      <button
        type="submit"
        disabled={pending || !sourceUri.startsWith("gs://")}
        className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
      >
        {pending ? "Preparing suggestion…" : "Suggest a camera move"}
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
