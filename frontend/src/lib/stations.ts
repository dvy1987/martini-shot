/** Operator-facing names and what each finishing stage does. */

export interface StationCopy {
  name: string;
  description: string;
}

export const INGEST_WATCH_DESCRIPTION =
  "Gemini watches each clip and writes the spoken words and a short scene description. Silence is allowed.";

const BOARD_STATION_ORDER = [
  "upload",
  "ingest",
  "loudness",
  "pickups",
  "extend",
  "corrections",
  "relight",
  "coverage",
  "camera_language",
  "dub",
  "delivery",
  "spend",
] as const;

export const STATION_COPY: Record<string, StationCopy> = {
  upload: {
    name: "Upload",
    description: "The clip arrives and we confirm the file opens. A broken file stops here.",
  },
  ingest: {
    name: "Ingest",
    description: INGEST_WATCH_DESCRIPTION,
  },
  loudness: {
    name: "Fix audio",
    description: "We listen to the clip, balance the mix, and keep continuing shots in the same family.",
  },
  pickups: {
    name: "Pickups",
    description: "We look at the picture after the mix and repair real flicker or damage. The original file stays.",
  },
  extend: {
    name: "Extend a shot",
    description: "We keep a shot rolling when the take ends too soon.",
  },
  corrections: {
    name: "Fix an image",
    description: "We change something in the picture without replacing the take.",
  },
  relight: {
    name: "Improve lighting",
    description: "We shift the lighting look on the existing shot.",
  },
  coverage: {
    name: "Add coverage",
    description: "We add another angle of the same moment.",
  },
  camera_language: {
    name: "Camera movement",
    description: "We change how the camera moves through the shot.",
  },
  dub: {
    name: "Create a dubbed version",
    description: "We fit a new language track to the picture.",
  },
  delivery: {
    name: "Delivery",
    description: "We check the finished clip against delivery rules. This always runs last.",
  },
  spend: {
    name: "Budget check",
    description: "We watch the budget and stop work that no longer fits.",
  },
};

export function stationName(station: string): string {
  return STATION_COPY[station]?.name ?? station.replaceAll("_", " ");
}

export function stationDescription(station: string): string {
  return STATION_COPY[station]?.description ?? "";
}

export function stationRank(station: string): number {
  const index = BOARD_STATION_ORDER.indexOf(station as (typeof BOARD_STATION_ORDER)[number]);
  return index === -1 ? BOARD_STATION_ORDER.length : index;
}
