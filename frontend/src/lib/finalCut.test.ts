import { describe, expect, it } from "vitest";

import { boardRows } from "@/lib/clipDisplay";
import {
  applyFinalCutPick,
  defaultFinalCutPick,
  downloadFinalCutBlobs,
  finalCutAction,
  finalCutPlaylist,
  finalCutSlots,
  groupBoardByClip,
  orchestratorHasStopped,
  type FinalCutPick,
} from "@/lib/finalCut";
import type { Job, Worklist } from "@/types/api";

function job(partial: Partial<Job> & Pick<Job, "job_id" | "station">): Job {
  return {
    project_id: "p1",
    input_refs: ["projects/p1/ingest/job-in/cafe.mp4"],
    status: "pass",
    attempts: 1,
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

describe("finalCut", () => {
  it("stays empty while the orchestrator is still running", () => {
    const ingest = job({
      job_id: "job-in-1",
      station: "ingest",
      result: { upload_index: 0, probe: { duration_s: 4 } },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const running = worklist({
      status: "running",
      phase: "executing",
      items: [{ id: "extend::a", station: "extend", status: "running" }],
    });
    expect(orchestratorHasStopped(running)).toBe(false);
    const slots = finalCutSlots([ingest, mixed], {}, running);
    expect(slots[0]?.pick).toBeNull();
  });

  it("treats waiting_for_budget with no active leftover items as stopped", () => {
    expect(
      orchestratorHasStopped(
        worklist({
          status: "waiting_for_budget",
          items: [{ id: "extend::a", station: "extend", status: "passed" }],
        }),
      ),
    ).toBe(true);
  });

  it("fills Final cut when the orchestrator stops even if leftover steps never ran", () => {
    const ingest = job({
      job_id: "job-in-1",
      station: "ingest",
      result: { upload_index: 0, ingested: true, scene: "Cafe." },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const stoppedShort = worklist({
      status: "waiting_for_budget",
      items: [
        { id: "loudness::a", station: "loudness", status: "passed" },
        { id: "extend::a", station: "extend", status: "waiting" },
      ],
    });
    expect(orchestratorHasStopped(stoppedShort)).toBe(true);
    const slots = finalCutSlots([ingest, mixed], {}, stoppedShort);
    expect(slots[0]?.pick).toEqual({ jobId: "job-loud-1", side: "after" });
  });

  it("uses the last station that successfully updated the clip, not a later failed or skipped step", () => {
    const origin = "projects/p1/ingest/job-in/cafe.mp4";
    const ingest = job({
      job_id: "job-in-1",
      station: "ingest",
      result: { upload_index: 0, ingested: true, scene: "Cafe." },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      input_refs: [origin],
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const pickupsUnchanged = job({
      job_id: "job-pick-1",
      station: "pickups",
      status: "pass",
      input_refs: [origin],
      result: {},
    });
    const extendFailed = job({
      job_id: "job-ext-1",
      station: "extend",
      status: "fail",
      input_refs: [origin],
      result: { artifact_ref: "projects/p1/mixes/a-extend.mp4" },
    });
    expect(defaultFinalCutPick([ingest, mixed, pickupsUnchanged, extendFailed], origin)).toEqual({
      jobId: "job-loud-1",
      side: "after",
    });
  });

  it("lines originals up in upload order and fills the latest After once the orchestrator stops", () => {
    const first = job({
      job_id: "job-in-1",
      station: "ingest",
      input_refs: ["projects/p1/ingest/job-in-1/a.mp4"],
      result: { upload_index: 0, probe: { duration_s: 4 } },
    });
    const second = job({
      job_id: "job-in-2",
      station: "ingest",
      input_refs: ["projects/p1/ingest/job-in-2/b.mp4"],
      result: { upload_index: 1, probe: { duration_s: 4 } },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      input_refs: first.input_refs,
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const stopped = worklist({
      status: "idle",
      items: [{ id: "loudness::a", station: "loudness", status: "passed" }],
    });
    expect(orchestratorHasStopped(stopped)).toBe(true);
    const slots = finalCutSlots([second, mixed, first], {}, stopped);
    expect(slots.map((slot) => slot.name)).toEqual(["a.mp4", "b.mp4"]);
    expect(slots[0]?.pick).toEqual({ jobId: "job-loud-1", side: "after" });
    expect(slots[1]?.pick).toEqual({ jobId: "job-in-2", side: "before" });
  });

  it("lets the operator replace the default After with another After of the same clip", () => {
    const ingest = job({
      job_id: "job-in-1",
      station: "ingest",
      result: { upload_index: 0, ingested: true, scene: "Cafe." },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const origin = ingest.input_refs[0] ?? "";
    const override: Record<string, FinalCutPick> = applyFinalCutPick({}, origin, {
      jobId: "job-in-1",
      side: "after",
    });
    const stopped = worklist({ status: "idle" });
    const slots = finalCutSlots([ingest, mixed], override, stopped);
    expect(slots[0]?.pick).toEqual({ jobId: "job-in-1", side: "after" });
    expect(defaultFinalCutPick([ingest, mixed], origin)).toEqual({
      jobId: "job-loud-1",
      side: "after",
    });
  });

  it("hides Final cut actions until the orchestrator has stopped", () => {
    const ingest = job({
      job_id: "job-in-1",
      station: "ingest",
      result: { upload_index: 0, ingested: true, scene: "Cafe." },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const rows = boardRows([ingest, mixed]);
    const mixAfter = rows.find((row) => row.displayStation === "loudness");
    expect(finalCutAction(mixAfter, null)).toBeNull();
  });

  it("labels only After versions in the Final cut column", () => {
    const ingest = job({
      job_id: "job-in-1",
      station: "ingest",
      result: { upload_index: 0, ingested: true, scene: "Cafe." },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const pick = defaultFinalCutPick([ingest, mixed], ingest.input_refs[0] ?? "");
    const rows = boardRows([ingest, mixed]);
    const ingestAfter = rows.find((row) => row.displayStation === "ingest");
    const mixAfter = rows.find((row) => row.displayStation === "loudness");
    expect(finalCutAction(ingestAfter, pick)).toBe("Add to final cut");
    expect(finalCutAction(mixAfter, pick)).toBe("Final Cut");
  });

  it("builds a playlist of selected After clips in upload order", () => {
    const first = job({
      job_id: "job-in-1",
      station: "ingest",
      input_refs: ["projects/p1/ingest/job-in-1/a.mp4"],
      result: { upload_index: 0, ingested: true, scene: "Cafe." },
    });
    const second = job({
      job_id: "job-in-2",
      station: "ingest",
      input_refs: ["projects/p1/ingest/job-in-2/b.mp4"],
      result: { upload_index: 1, ingested: true, scene: "Street." },
    });
    const mixed = job({
      job_id: "job-loud-1",
      station: "loudness",
      input_refs: first.input_refs,
      result: { artifact_ref: "projects/p1/mixes/a-loud.mp4" },
    });
    const slots = finalCutSlots([second, mixed, first], {}, worklist({ status: "idle" }));
    expect(finalCutPlaylist(slots)).toEqual([
      { jobId: "job-loud-1", side: "after", name: "a.mp4" },
      { jobId: "job-in-2", side: "after", name: "b.mp4" },
    ]);
  });

  it("downloads every playlist clip before returning object URLs", async () => {
    const order: string[] = [];
    const urls = await downloadFinalCutBlobs(
      [
        { jobId: "job-a", side: "after", name: "a.mp4" },
        { jobId: "job-b", side: "before", name: "b.mp4" },
      ],
      {
        getClip: async (jobId, side) => {
          order.push(`clip:${jobId}:${side}`);
          return {
            job_id: jobId,
            side,
            clip_name: jobId,
            url: `/media/${jobId}.mp4`,
            expires_in_minutes: 15,
            metadata: {},
          };
        },
        fetchBlob: async (url) => {
          order.push(`blob:${url}`);
          return new Blob(["clip"], { type: "video/mp4" });
        },
        toObjectUrl: (blob) => `blob:${blob.size}`,
      },
    );
    expect(order).toEqual([
      "clip:job-a:after",
      "blob:/media/job-a.mp4",
      "clip:job-b:before",
      "blob:/media/job-b.mp4",
    ]);
    expect(urls).toEqual(["blob:4", "blob:4"]);
  });
});

describe("groupBoardByClip", () => {
  it("keeps each original clip's station journey together and numbers them Clip 1, Clip 2", () => {
    const cafe = "projects/p1/ingest/in-1/cafe.mp4";
    const street = "projects/p1/ingest/in-2/street.mp4";
    const ingestStreet = job({
      job_id: "in-2",
      station: "ingest",
      input_refs: [street],
      result: { upload_index: 1, ingested: true },
    });
    const ingestCafe = job({
      job_id: "in-1",
      station: "ingest",
      input_refs: [cafe],
      result: { upload_index: 0, ingested: true },
    });
    const mixCafe = job({
      job_id: "loud-1",
      station: "loudness",
      input_refs: ["projects/p1/ingest/in-1/cafe-loud.mp4"],
      result: { artifact_ref: "projects/p1/ingest/in-1/cafe-loud.mp4" },
    });
    const grouped = groupBoardByClip([ingestStreet, mixCafe, ingestCafe]);
    expect(grouped.map((group) => group.label)).toEqual(["Clip 1", "Clip 2"]);
    expect(grouped[0]?.rows.map((row) => row.displayStation)).toEqual([
      "upload",
      "ingest",
      "loudness",
    ]);
    expect(grouped[1]?.rows.map((row) => row.displayStation)).toEqual(["upload", "ingest"]);
  });

  it("keeps re-edits that consume generated artifacts in the original shot group", () => {
    const origin = "projects/p1/ingest/in-1/cafe.mp4";
    const ingest = job({
      job_id: "in-1",
      station: "ingest",
      input_refs: [origin],
      result: { upload_index: 0, shot_id: "shot-1", probe: { duration_s: 4 } },
    });
    const mix = job({
      job_id: "loud-1",
      station: "loudness",
      input_refs: [origin],
      result: { shot_id: "shot-1", artifact_ref: "projects/p1/loudness/loud-1.mp4" },
    });
    const relight = job({
      job_id: "relight-1",
      station: "relight",
      input_refs: ["projects/p1/loudness/loud-1.mp4"],
      result: {
        shot_id: "shot-1",
        artifact_ref: "projects/p1/relight/relight-1.mp4",
      },
    });
    const grouped = groupBoardByClip([ingest, mix, relight]);

    expect(grouped).toHaveLength(1);
    expect(grouped[0]?.rows.map((row) => row.displayStation)).toEqual([
      "upload",
      "ingest",
      "loudness",
      "relight",
    ]);
  });
});
