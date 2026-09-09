/** Plain-language reading of what a station agent saw, ignored, fixed, or failed. */

import { stationName } from "@/lib/stations";
import type { Job } from "@/types/api";

export interface AgentNotes {
  changed: string;
  problem: string;
  ignored: string;
  fixed: string;
  failed: string;
}

const QUESTION_HEADING =
  /^(what they thought the problem was|what they ignored|what they fixed|where they failed)\s*:?\s*/i;

export function composeAgentNotes(notes: AgentNotes): string {
  const pending = /has not finished looking|has not written notes/i.test(notes.problem);
  const paragraphs: string[] = [];
  const add = (value: string) => {
    const clean = stripQuestionHeading(value);
    if (!clean) return;
    const already = paragraphs.join(" ").toLowerCase().includes(clean.toLowerCase().slice(0, 48));
    if (!already) paragraphs.push(clean);
  };
  add(notes.problem || "This step has not written notes yet.");
  if (pending) return paragraphs.join("\n\n");
  add(notes.ignored || "The agent did not set anything aside.");
  add(notes.fixed || "The agent did not keep a change.");
  add(notes.failed || "This step succeeded.");
  return paragraphs.join("\n\n");
}

function stripQuestionHeading(value: string): string {
  return value.trim().replace(QUESTION_HEADING, "").trim();
}

export function readAgentNotes(job: Job, displayStation = job.station): AgentNotes {
  const result = job.result ?? {};
  const agent = asRecord(result.agent);
  const reason = text(agent?.reason);
  const stage = displayStation === "upload" ? "upload" : job.station;

  if (PENDING.has(job.status) && !reason && Object.keys(result).length === 0) {
    return {
      changed: "Still working",
      problem: "This step has not finished looking yet.",
      ignored: "",
      fixed: "",
      failed: "",
    };
  }

  if (stage === "upload") {
    return uploadNotes(job);
  }
  if (stage === "ingest") {
    return ingestNotes(job, reason);
  }
  if (stage === "loudness") {
    return loudnessNotes(job, reason);
  }
  if (stage === "pickups") {
    return pickupsNotes(job, reason);
  }
  if (stage === "delivery") {
    return deliveryNotes(job, reason);
  }
  return generativeNotes(job, reason, stage);
}

function uploadNotes(job: Job): AgentNotes {
  if (job.status === "pass") {
    return {
      changed: "File opened",
      problem: "The agent only needed to know the file would open.",
      ignored: "The agent did not judge the mix, the picture, or the lighting. That comes later.",
      fixed: "The file opened and passed the check.",
      failed: "",
    };
  }
  if (FAILED.has(job.status)) {
    return {
      changed: "File did not open",
      problem: "The agent tried to open the file.",
      ignored: "",
      fixed: "",
      failed: plainError(job) || "The file would not open. A broken file stops here.",
    };
  }
  return {
    changed: "Still checking the file",
    problem: "The agent is confirming the file opens.",
    ignored: "",
    fixed: "",
    failed: "",
  };
}

function ingestNotes(job: Job, reason: string): AgentNotes {
  const spoken = text(job.result?.spoken_words);
  const scene = text(job.result?.scene);
  const wrote = Boolean(spoken || scene);
  if (FAILED.has(job.status)) {
    return {
      changed: "Watch did not finish",
      problem: reason || "The agent tried to watch the clip and write what happens.",
      ignored: "",
      fixed: "",
      failed: plainError(job) || "The watch did not finish.",
    };
  }
  return {
    changed: wrote ? "Wrote the spoken words and scene" : "Watched the clip",
    problem: reason || "The agent needed the spoken words and a short scene so future steps are not guessing.",
    ignored: "The agent did not mix, repair flicker, or change the lighting.",
    fixed: wrote
      ? [spoken ? `Spoken words: ${spoken}` : "", scene ? `Scene: ${scene}` : ""].filter(Boolean).join(" ")
      : "The agent watched the clip. Notes have not been written yet.",
    failed: "",
  };
}

function loudnessNotes(job: Job, reason: string): AgentNotes {
  const result = job.result ?? {};
  const stems = text(result.stems);
  const mixed = result.mixed === true;
  const verdict = text(result.verdict);
  const ignored =
    stems === "balanced"
      ? "The agent did not treat the weather as louder than the voices. The meter called speech and the rest of the soundtrack balanced."
      : stems === "music_hot"
        ? ""
        : "The agent judged overall loudness, not a full creative remix.";
  let failed = "";
  if (FAILED.has(job.status)) {
    failed = plainError(job) || "The mix did not finish.";
  } else if (verdict === "fail_true_peak") {
    failed = "A peak was still too hot after the mix, even though this step was marked complete.";
  }
  return {
    changed: mixed ? "Mixed the soundtrack" : FAILED.has(job.status) ? "Mix did not finish" : "Listened to the soundtrack",
    problem: reason || "The agent checked whether the soundtrack sits at a comfortable streaming level.",
    ignored,
    fixed: mixed
      ? "The agent mixed the soundtrack toward the streaming target and kept speech in the same family as the last clip."
      : "",
    failed,
  };
}

function pickupsNotes(job: Job, reason: string): AgentNotes {
  const result = job.result ?? {};
  const flicker = asRecord(result.flicker);
  const score = typeof flicker?.flicker_score === "number" ? flicker.flicker_score : null;
  const repaired = result.repaired === true;
  const ignored =
    flicker?.ok === true || (score != null && score < 0.18)
      ? "The agent did not call this flicker. The flicker number stayed under the house limit."
      : "";
  if (FAILED.has(job.status)) {
    return {
      changed: "Picture repair failed",
      problem: reason || "The agent looked for flicker or damaged frames.",
      ignored,
      fixed: "",
      failed: plainError(job) || "The picture repair did not finish.",
    };
  }
  return {
    changed: repaired ? "Repaired the picture" : "Left the picture",
    problem: reason || "The agent looked for flicker or damaged frames.",
    ignored,
    fixed: repaired
      ? "The agent re-rendered the picture and kept the new take."
      : "The agent left the original picture. No repair was kept.",
    failed: "",
  };
}

function deliveryNotes(job: Job, reason: string): AgentNotes {
  const delivery = asRecord(job.result?.delivery);
  const violations = Array.isArray(delivery?.violations) ? delivery.violations : [];
  const lines = violations
    .map((row) => {
      const item = asRecord(row);
      return item ? plainDeliveryViolation(text(item.message)) : "";
    })
    .filter(Boolean);
  if (FAILED.has(job.status) || lines.length > 0) {
    return {
      changed: "Delivery check did not pass",
      problem: reason || "The agent checked the finished clip against the delivery rules.",
      ignored: "The agent was not judging the story. This is a shipment check.",
      fixed: job.result?.caption_ref ? "The agent wrote captions." : "",
      failed: lines.join(" ") || plainError(job) || "The delivery check did not pass.",
    };
  }
  return {
    changed: "Passed the delivery check",
    problem: reason || "The agent checked the finished clip against the delivery rules.",
    ignored: "The agent was not judging the story. This is a shipment check.",
    fixed: "The clip met the delivery rules.",
    failed: "",
  };
}

function generativeNotes(job: Job, reason: string, stage: string): AgentNotes {
  const result = job.result ?? {};
  const intent = text(result.intent) || reason;
  const name = stationName(stage);
  if (FAILED.has(job.status)) {
    return {
      changed: `Could not finish ${name.toLowerCase()}`,
      problem: intent || `The agent tried to run ${name.toLowerCase()}.`,
      ignored: "",
      fixed: "",
      failed: plainError(job) || `${name} did not finish.`,
    };
  }
  if (job.status === "pass" && text(result.artifact_ref)) {
    return {
      changed: `Finished ${name.toLowerCase()}`,
      problem: intent || `The agent ran ${name.toLowerCase()} on this clip.`,
      ignored: "",
      fixed: `The agent kept a new take from ${name.toLowerCase()}. The original file stays.`,
      failed: "",
    };
  }
  if (PENDING.has(job.status)) {
    return {
      changed: "Still working",
      problem: intent || `The agent is still on ${name.toLowerCase()}.`,
      ignored: "",
      fixed: "",
      failed: "",
    };
  }
  return {
    changed: "No new take",
    problem: intent || `The agent looked at whether ${name.toLowerCase()} was needed.`,
    ignored: reason ? "" : `The agent did not keep a new ${name.toLowerCase()} take.`,
    fixed: "",
    failed: "",
  };
}

function plainError(job: Job): string {
  const raw = job.error;
  const message =
    raw && typeof raw === "object" && "message" in raw ? text(raw.message) : text(raw);
  const duration = message.match(/duration\s+(\d+(?:\.\d+)?)\s+exceeds maximum duration\s+(\d+(?:\.\d+)?)/i);
  if (duration) {
    return `The clip is ${duration[1]} seconds. This edit only allows ${duration[2]} seconds.`;
  }
  const nested = message.match(/'message':\s*'([^']+)'/);
  if (nested?.[1]) {
    return nested[1];
  }
  if (message === "delivery_fail") {
    return "The delivery check did not pass.";
  }
  return message.replace(/^Error code:\s*\d+\s*-\s*/i, "").trim();
}

function plainDeliveryViolation(message: string): string {
  const fps = message.match(/fps\s+([\d.]+)\s+outside/i);
  if (fps) {
    return `The frame rate is ${Number(fps[1]).toFixed(2)} frames per second, which is outside the allowed range.`;
  }
  return message;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

const PENDING = new Set(["queued", "running"]);
const FAILED = new Set(["fail", "quarantined", "needs_human", "throttled"]);
