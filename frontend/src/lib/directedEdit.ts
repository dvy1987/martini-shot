/** Studio redesign (2026-09-09): pure logic for the Directed Edit screen —
 * clip selection, station/camera-movement/chat gating, and the
 * clarify-round bookkeeping. Kept side-effect free so it is unit-testable
 * without a backend (frontend/AGENTS.md: components never call fetch
 * directly, and this module never does either). */

import type { FinalCutSlot } from "@/lib/finalCut";
import type { DirectedEditTurn, ShotRow, Worklist } from "@/types/api";

/** The backend allows relight/coverage/camera_language/corrections
 * (DIRECTED_EDIT_STATIONS in backend/api/spine.py). camera_language gets
 * its own line with a movement-preset sub-panel, so the plain multi-select
 * toggle row is the other 3. */
export const DIRECTED_EDIT_TOGGLE_STATIONS = ["relight", "coverage", "corrections"] as const;

export const CAMERA_LANGUAGE_STATION = "camera_language" as const;

/** Mirrors backend/supervisor/station_agents/directed_edit.py MAX_QUESTIONS
 * — a defensive client-side stop so a misbehaving agent response can never
 * spin the clarify loop forever, even though the server already hard-gates
 * at this count. */
export const MAX_CLARIFY_QUESTIONS = 5;

function alternateArtifactRef(shot: ShotRow): string | null {
  const current = shot.alternates.find(
    (alternate) => alternate.alternate_id === shot.current_alternate_id,
  );
  if (current?.artifact_ref) return current.artifact_ref;
  const anyAlternate = shot.alternates.find((alternate) => alternate.artifact_ref);
  return anyAlternate?.artifact_ref ?? null;
}

/** The gs:// URI to send as source_uri for a new edit on this shot: the
 * current alternate first, then any alternate, then the original ingest
 * clip recorded on the worklist (RelightControls' defaultSourceUri
 * precedent, extended with the original-clip fallback so a freshly
 * ingested shot with no alternates yet is still editable here). */
export function currentSourceUri(shot: ShotRow, worklist: Worklist | null): string {
  return (
    alternateArtifactRef(shot) ?? worklist?.source_by_shot?.[shot.shot_id] ?? ""
  );
}

/** worklist.source_by_shot is shot_id -> origin; the filmstrip needs the
 * reverse to go from a selected clip (origin) back to its shot_id. */
export function originToShotId(worklist: Worklist | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [shotId, origin] of Object.entries(worklist?.source_by_shot ?? {})) {
    if (shotId && origin) out[origin] = shotId;
  }
  return out;
}

/** Left-to-right filmstrip order: worklist.shot_order when every slot
 * resolves to a shot, else the given (already stable) order. */
export function orderedFinalCutSlots(
  slots: readonly FinalCutSlot[],
  worklist: Worklist | null,
): FinalCutSlot[] {
  const shotIdByOrigin = originToShotId(worklist);
  const order = worklist?.shot_order;
  if (!order || !slots.every((slot) => shotIdByOrigin[slot.origin] !== undefined)) {
    return [...slots];
  }
  return [...slots].sort((left, right) => {
    const leftOrder = order[shotIdByOrigin[left.origin] ?? ""] ?? Number.POSITIVE_INFINITY;
    const rightOrder = order[shotIdByOrigin[right.origin] ?? ""] ?? Number.POSITIVE_INFINITY;
    return leftOrder - rightOrder;
  });
}

export interface GoGateInput {
  hasSelectedClip: boolean;
  stations: readonly string[];
  cameraMovement: string | null;
  chatText: string;
}

/** Go is enabled only once a clip is selected AND the operator has given
 * the agent something to act on: a station, a camera movement, or typed
 * text. */
export function canGo(input: GoGateInput): boolean {
  if (!input.hasSelectedClip) return false;
  return input.stations.length > 0 || input.cameraMovement !== null || input.chatText.trim() !== "";
}

export interface DirectedEditSelection {
  stations: readonly string[];
  cameraMovement: string | null;
  chatText: string;
  turns: readonly DirectedEditTurn[];
}

/** Builds the exact POST body for /directed-edit/clarify from the current
 * selection state. */
export function buildDirectedEditBrief(selection: DirectedEditSelection): {
  stations: string[];
  camera_movement: string | null;
  chat_text: string;
  turns: DirectedEditTurn[];
} {
  return {
    stations: [...selection.stations],
    camera_movement: selection.cameraMovement,
    chat_text: selection.chatText,
    turns: [...selection.turns],
  };
}

export function nextTurnsAfterAnswer(
  turns: readonly DirectedEditTurn[],
  question: string,
  answer: string,
): DirectedEditTurn[] {
  return [...turns, { question, answer }];
}
