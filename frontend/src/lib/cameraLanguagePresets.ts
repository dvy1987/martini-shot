/** Studio redesign (2026-09-09): the 5 camera movements shown as one-click
 * presets when the operator turns on "Camera movement". This is a curated
 * subset of the full approved vocabulary in
 * backend/stations/camera_language/run.py MOVEMENTS — kept intentionally
 * short (5 of 8) so the panel reads as a quick picker, not a spec sheet.
 * Labels/descriptions mirror the backend's own wording so the operator and
 * the agent are never describing two different things. */

export interface CameraMovementPreset {
  id: string;
  label: string;
  description: string;
}

export const CAMERA_MOVEMENT_PRESETS: readonly CameraMovementPreset[] = [
  {
    id: "handheld_shaky",
    label: "Shaky handheld",
    description: "Handheld camera with natural human shake.",
  },
  {
    id: "steadicam",
    label: "Steadicam glide",
    description: "A smooth, floating Steadicam move.",
  },
  {
    id: "dolly_zoom",
    label: "Dolly zoom",
    description: "Vertigo effect: dolly one way while zooming the other.",
  },
  {
    id: "crash_zoom",
    label: "Crash zoom",
    description: "An abrupt, fast crash zoom onto the subject.",
  },
  {
    id: "whip_pan",
    label: "Whip pan",
    description: "A fast whip pan between two points of interest.",
  },
] as const;

export function cameraMovementLabel(id: string): string {
  return CAMERA_MOVEMENT_PRESETS.find((preset) => preset.id === id)?.label ?? id;
}
