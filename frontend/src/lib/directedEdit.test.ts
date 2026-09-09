import { describe, expect, it } from "vitest";

import {
  buildDirectedEditBrief,
  canGo,
  currentSourceUri,
  DIRECTED_EDIT_TOGGLE_STATIONS,
  MAX_CLARIFY_QUESTIONS,
  nextTurnsAfterAnswer,
  originToShotId,
  orderedFinalCutSlots,
} from "@/lib/directedEdit";
import type { FinalCutSlot } from "@/lib/finalCut";
import type { ShotRow, Worklist } from "@/types/api";

function shot(partial: Partial<ShotRow> & Pick<ShotRow, "shot_id">): ShotRow {
  return {
    title: null,
    locked: false,
    current_alternate_id: null,
    alternates: [],
    ...partial,
  };
}

function worklist(partial: Partial<Worklist> = {}): Worklist {
  return {
    project_id: "p1",
    budget_micros: 1,
    spent_micros: 0,
    status: "idle",
    attendance: [],
    items: [],
    final_refs: [],
    original_refs: [],
    ...partial,
  };
}

describe("DIRECTED_EDIT_TOGGLE_STATIONS", () => {
  it("is the 3 plain toggle stations, camera_language is handled separately with its own presets", () => {
    expect(DIRECTED_EDIT_TOGGLE_STATIONS).toEqual(["relight", "coverage", "corrections"]);
  });
});

describe("currentSourceUri", () => {
  it("prefers the shot's current alternate artifact_ref", () => {
    const row = shot({
      shot_id: "s1",
      current_alternate_id: "alt-2",
      alternates: [
        { alternate_id: "alt-1", artifact_ref: "gs://bucket/alt-1.mp4" },
        { alternate_id: "alt-2", artifact_ref: "gs://bucket/alt-2.mp4" },
      ],
    });
    expect(currentSourceUri(row, null)).toBe("gs://bucket/alt-2.mp4");
  });

  it("falls back to any alternate with an artifact_ref when current_alternate_id is stale", () => {
    const row = shot({
      shot_id: "s1",
      current_alternate_id: "missing",
      alternates: [{ alternate_id: "alt-1", artifact_ref: "gs://bucket/alt-1.mp4" }],
    });
    expect(currentSourceUri(row, null)).toBe("gs://bucket/alt-1.mp4");
  });

  it("falls back to the worklist's original source_by_shot when there are no alternates yet", () => {
    const row = shot({ shot_id: "s1", alternates: [] });
    const wl = worklist({ source_by_shot: { s1: "gs://bucket/original.mp4" } });
    expect(currentSourceUri(row, wl)).toBe("gs://bucket/original.mp4");
  });

  it("returns an empty string when no source can be resolved at all", () => {
    const row = shot({ shot_id: "s1", alternates: [] });
    expect(currentSourceUri(row, null)).toBe("");
  });
});

describe("originToShotId", () => {
  it("inverts worklist.source_by_shot (shot_id -> origin) to origin -> shot_id", () => {
    const wl = worklist({
      source_by_shot: { "shot-1": "gs://bucket/a.mp4", "shot-2": "gs://bucket/b.mp4" },
    });
    expect(originToShotId(wl)).toEqual({
      "gs://bucket/a.mp4": "shot-1",
      "gs://bucket/b.mp4": "shot-2",
    });
  });

  it("returns an empty map for a null worklist", () => {
    expect(originToShotId(null)).toEqual({});
  });
});

describe("orderedFinalCutSlots", () => {
  const slots: FinalCutSlot[] = [
    { origin: "gs://bucket/b.mp4", name: "Clip B", pick: null },
    { origin: "gs://bucket/a.mp4", name: "Clip A", pick: null },
    { origin: "gs://bucket/c.mp4", name: "Clip C", pick: null },
  ];

  it("orders slots by worklist.shot_order when every origin resolves to a shot", () => {
    const wl = worklist({
      source_by_shot: {
        "shot-a": "gs://bucket/a.mp4",
        "shot-b": "gs://bucket/b.mp4",
        "shot-c": "gs://bucket/c.mp4",
      },
      shot_order: { "shot-a": 0, "shot-b": 1, "shot-c": 2 },
    });
    expect(orderedFinalCutSlots(slots, wl).map((slot) => slot.origin)).toEqual([
      "gs://bucket/a.mp4",
      "gs://bucket/b.mp4",
      "gs://bucket/c.mp4",
    ]);
  });

  it("keeps the given order (stable) when there is no worklist or shot_order", () => {
    expect(orderedFinalCutSlots(slots, null).map((slot) => slot.origin)).toEqual([
      "gs://bucket/b.mp4",
      "gs://bucket/a.mp4",
      "gs://bucket/c.mp4",
    ]);
  });
});

describe("canGo", () => {
  it("is false with no clip selected, regardless of everything else", () => {
    expect(
      canGo({ hasSelectedClip: false, stations: ["relight"], cameraMovement: null, chatText: "" }),
    ).toBe(false);
  });

  it("is false with a clip selected but nothing chosen and no chat text", () => {
    expect(
      canGo({ hasSelectedClip: true, stations: [], cameraMovement: null, chatText: "   " }),
    ).toBe(false);
  });

  it("is true with a clip and at least one station", () => {
    expect(
      canGo({ hasSelectedClip: true, stations: ["relight"], cameraMovement: null, chatText: "" }),
    ).toBe(true);
  });

  it("is true with a clip and a camera movement, no stations or chat", () => {
    expect(
      canGo({ hasSelectedClip: true, stations: [], cameraMovement: "steadicam", chatText: "" }),
    ).toBe(true);
  });

  it("is true with a clip and only typed chat text", () => {
    expect(
      canGo({
        hasSelectedClip: true,
        stations: [],
        cameraMovement: null,
        chatText: "make it moodier",
      }),
    ).toBe(true);
  });
});

describe("buildDirectedEditBrief", () => {
  it("builds the clarify request body from the current selections and transcript", () => {
    expect(
      buildDirectedEditBrief({
        stations: ["relight", "camera_language"],
        cameraMovement: "handheld_shaky",
        chatText: "  make it tense  ",
        turns: [{ question: "Q1?", answer: "A1" }],
      }),
    ).toEqual({
      stations: ["relight", "camera_language"],
      camera_movement: "handheld_shaky",
      chat_text: "  make it tense  ",
      turns: [{ question: "Q1?", answer: "A1" }],
    });
  });
});

describe("nextTurnsAfterAnswer", () => {
  it("appends the question/answer pair", () => {
    expect(nextTurnsAfterAnswer([], "Q1?", "A1")).toEqual([{ question: "Q1?", answer: "A1" }]);
  });

  it("never mutates the input array", () => {
    const turns = [{ question: "Q1?", answer: "A1" }];
    const next = nextTurnsAfterAnswer(turns, "Q2?", "A2");
    expect(turns).toHaveLength(1);
    expect(next).toHaveLength(2);
  });
});

describe("MAX_CLARIFY_QUESTIONS", () => {
  it("mirrors the backend directed_edit agent's hard cap (defensive client-side stop)", () => {
    expect(MAX_CLARIFY_QUESTIONS).toBe(5);
  });
});
