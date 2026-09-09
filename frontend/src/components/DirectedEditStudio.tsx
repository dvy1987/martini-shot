import { useEffect, useMemo, useState } from "react";

import {
  clarifyDirectedEdit,
  decideApproval,
  getAlternateMedia,
  promoteAlternate,
  proposeCorrection,
} from "@/api/endpoints";
import { CAMERA_MOVEMENT_PRESETS } from "@/lib/cameraLanguagePresets";
import {
  buildDirectedEditBrief,
  canGo,
  CAMERA_LANGUAGE_STATION,
  currentSourceUri,
  DIRECTED_EDIT_TOGGLE_STATIONS,
  MAX_CLARIFY_QUESTIONS,
  nextTurnsAfterAnswer,
  orderedFinalCutSlots,
  originToShotId,
} from "@/lib/directedEdit";
import { finalCutSlots } from "@/lib/finalCut";
import { stationName } from "@/lib/stations";
import ClipReviewModal from "@/components/ClipReviewModal";
import ClipThumb from "@/components/ClipThumb";
import type { DirectedEditTurn, Job, JobClip, ShotRow, Worklist } from "@/types/api";

interface DirectedEditStudioProps {
  projectId: string;
  shots: ShotRow[];
  jobs: Job[];
  worklist: Worklist | null;
  clarify?: typeof clarifyDirectedEdit;
  propose?: typeof proposeCorrection;
  decide?: typeof decideApproval;
  promote?: typeof promoteAlternate;
  fetchMediaUrl?: (alternateId: string) => Promise<string>;
}

type Phase = "idle" | "asking" | "generating" | "done" | "error";

const TERMINAL_FAIL_STATUSES = new Set(["fail", "quarantined", "needs_human"]);

function resultAlternateIdFromJob(job: Job | undefined): string | null {
  const value = job?.result?.alternate_id;
  return typeof value === "string" && value ? value : null;
}

export default function DirectedEditStudio({
  projectId,
  shots,
  jobs,
  worklist,
  clarify = clarifyDirectedEdit,
  propose = proposeCorrection,
  decide = decideApproval,
  promote = promoteAlternate,
  fetchMediaUrl = (alternateId: string) => getAlternateMedia(alternateId).then((media) => media.url),
}: DirectedEditStudioProps) {
  const [selectedOrigin, setSelectedOrigin] = useState<string | null>(null);
  const [stations, setStations] = useState<string[]>([]);
  const [cameraPanelOpen, setCameraPanelOpen] = useState(false);
  const [cameraMovement, setCameraMovement] = useState<string | null>(null);
  const [chatText, setChatText] = useState("");
  const [turns, setTurns] = useState<DirectedEditTurn[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [answerDraft, setAnswerDraft] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [resultAlternateId, setResultAlternateId] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [promoted, setPromoted] = useState(false);
  const [reviewClip, setReviewClip] = useState<JobClip | null>(null);

  const slots = useMemo(
    () => orderedFinalCutSlots(finalCutSlots(jobs, {}, worklist), worklist),
    [jobs, worklist],
  );
  const shotIdByOrigin = useMemo(() => originToShotId(worklist), [worklist]);
  const selectedShotId = selectedOrigin ? shotIdByOrigin[selectedOrigin] ?? null : null;
  const selectedShot = selectedShotId
    ? shots.find((row) => row.shot_id === selectedShotId) ?? null
    : null;
  const sourceUri = selectedShot ? currentSourceUri(selectedShot, worklist) : "";

  function resetForNewClip(origin: string) {
    setSelectedOrigin(origin);
    setStations([]);
    setCameraPanelOpen(false);
    setCameraMovement(null);
    setChatText("");
    setTurns([]);
    setPendingQuestion(null);
    setAnswerDraft("");
    setPhase("idle");
    setError(null);
    setTrackedJobId(null);
    setResultAlternateId(null);
    setVideoUrl(null);
    setPromoted(false);
  }

  function toggleStation(station: string) {
    setStations((current) =>
      current.includes(station)
        ? current.filter((row) => row !== station)
        : [...current, station],
    );
  }

  function toggleCameraPanel() {
    setCameraPanelOpen((open) => {
      if (open) setCameraMovement(null);
      return !open;
    });
  }

  function pickMovement(id: string) {
    setCameraMovement((current) => (current === id ? null : id));
  }

  async function runClarify(nextTurns: DirectedEditTurn[]) {
    if (!selectedShotId) return;
    setError(null);
    try {
      const brief = buildDirectedEditBrief({
        stations,
        cameraMovement,
        chatText,
        turns: nextTurns,
      });
      const response = await clarify(selectedShotId, brief);
      if (response.decision === "ask" && nextTurns.length < MAX_CLARIFY_QUESTIONS && response.question) {
        setPendingQuestion(response.question);
        setPhase("asking");
        return;
      }
      const finalIntent =
        response.final_intent?.trim() || chatText.trim() || "Apply a light, tasteful pass on this clip.";
      await generate(finalIntent);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The agent could not be reached.");
      setPhase("error");
    }
  }

  async function generate(finalIntent: string) {
    if (!selectedShotId || !sourceUri) {
      setError("This clip has no known source file yet.");
      setPhase("error");
      return;
    }
    setPendingQuestion(null);
    setPhase("generating");
    try {
      const proposed = await propose(selectedShotId, {
        source_uri: sourceUri,
        intent: finalIntent,
        reason: "Studio directed edit",
      });
      const approval = await decide(proposed.approval_id, "approve");
      if (approval.status === "failed") {
        throw new Error("The edit could not be started.");
      }
      setTrackedJobId(approval.job_id ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The edit could not be started.");
      setPhase("error");
    }
  }

  function go() {
    if (
      !canGo({
        hasSelectedClip: selectedOrigin !== null,
        stations,
        cameraMovement,
        chatText,
      })
    ) {
      return;
    }
    void runClarify(turns);
  }

  async function sendAnswer() {
    if (!pendingQuestion) return;
    const next = nextTurnsAfterAnswer(turns, pendingQuestion, answerDraft);
    setTurns(next);
    setAnswerDraft("");
    await runClarify(next);
  }

  useEffect(() => {
    if (!trackedJobId || phase !== "generating") return;
    const found = jobs.find((row) => row.job_id === trackedJobId);
    if (!found) return;
    if (found.status === "pass") {
      const alternateId = resultAlternateIdFromJob(found);
      if (alternateId) {
        setResultAlternateId(alternateId);
        setPhase("done");
      }
      return;
    }
    if (TERMINAL_FAIL_STATUSES.has(found.status)) {
      setError(found.error?.message ?? "The edit job did not finish successfully.");
      setPhase("error");
    }
  }, [jobs, trackedJobId, phase]);

  useEffect(() => {
    if (phase !== "done" || !resultAlternateId) return;
    let cancelled = false;
    void fetchMediaUrl(resultAlternateId)
      .then((url) => {
        if (!cancelled) setVideoUrl(url);
      })
      .catch(() => {
        // Playback stays unavailable; add-to-final-cut still works without it.
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, resultAlternateId]);

  async function addToFinalCut() {
    if (!selectedShotId || !resultAlternateId) return;
    setError(null);
    try {
      const proposed = await promote(selectedShotId, { alternate_id: resultAlternateId });
      const approval = await decide(proposed.approval_id, "approve");
      if (approval.status === "failed") {
        throw new Error("Could not add this version to the final cut.");
      }
      setPromoted(true);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not add this version to the final cut.",
      );
    }
  }

  const goEnabled = canGo({
    hasSelectedClip: selectedOrigin !== null,
    stations,
    cameraMovement,
    chatText,
  });

  return (
    <section
      aria-labelledby="directed-edit-heading"
      className="mt-8 rounded-md border border-line bg-surface-1 p-4"
      data-project-id={projectId}
    >
      <h2
        id="directed-edit-heading"
        className="font-mono text-xs uppercase tracking-widest text-ink-muted"
      >
        Directed edit
      </h2>
      <p className="mt-2 text-sm text-ink-muted">
        Pick one clip, tell Martini Shot what to change, and it will ask up to 5 quick
        questions before creating one new version. Nothing replaces the current cut until
        you add it.
      </p>

      {slots.length === 0 ? (
        <p className="mt-4 font-mono text-xs uppercase tracking-wider text-ink-muted">
          No clips are ready yet.
        </p>
      ) : (
        <ol className="mt-4 flex min-w-0 gap-3 overflow-x-auto pb-2">
          {slots.map((slot, index) => {
            const shotId = shotIdByOrigin[slot.origin];
            const shot = shotId ? shots.find((row) => row.shot_id === shotId) : undefined;
            const displayName = shot?.title?.trim() || slot.name;
            const isSelected = slot.origin === selectedOrigin;
            return (
              <li key={slot.origin} className="min-w-28 shrink-0">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                  Clip {index + 1}
                </p>
                {slot.pick ? (
                  <ClipThumb
                    jobId={slot.pick.jobId}
                    side={slot.pick.side}
                    label={displayName}
                    reviewSide="after"
                    onOpen={setReviewClip}
                  />
                ) : (
                  <p className="text-xs text-ink-muted">Not ready yet</p>
                )}
                <button
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => resetForNewClip(slot.origin)}
                  className={`mt-1 w-full rounded-sm border px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ease-chrome focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten ${
                    isSelected
                      ? "border-tungsten text-tungsten"
                      : "border-line text-ink-muted hover:border-ink-muted"
                  }`}
                >
                  {isSelected ? "Selected" : `Select ${displayName}`}
                </button>
              </li>
            );
          })}
        </ol>
      )}

      {selectedOrigin ? (
        <div className="mt-5 space-y-3 border-t border-dashed border-line pt-4">
          <div className="flex flex-wrap gap-2">
            {DIRECTED_EDIT_TOGGLE_STATIONS.map((station) => (
              <button
                key={station}
                type="button"
                aria-pressed={stations.includes(station)}
                disabled={phase !== "idle"}
                onClick={() => toggleStation(station)}
                className={`rounded-sm border px-2 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors ease-chrome focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:opacity-50 ${
                  stations.includes(station)
                    ? "border-tungsten text-tungsten"
                    : "border-line text-ink hover:border-ink-muted"
                }`}
              >
                {stationName(station)}
              </button>
            ))}
          </div>

          <div>
            <button
              type="button"
              aria-pressed={cameraPanelOpen}
              disabled={phase !== "idle"}
              onClick={toggleCameraPanel}
              className={`rounded-sm border px-2 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors ease-chrome focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:opacity-50 ${
                cameraPanelOpen
                  ? "border-tungsten text-tungsten"
                  : "border-line text-ink hover:border-ink-muted"
              }`}
            >
              {stationName(CAMERA_LANGUAGE_STATION)}
            </button>
            {cameraPanelOpen ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {CAMERA_MOVEMENT_PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    aria-pressed={cameraMovement === preset.id}
                    disabled={phase !== "idle"}
                    onClick={() => pickMovement(preset.id)}
                    title={preset.description}
                    className={`rounded-sm border px-2 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors ease-chrome focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:opacity-50 ${
                      cameraMovement === preset.id
                        ? "border-tungsten text-tungsten"
                        : "border-line text-ink hover:border-ink-muted"
                    }`}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <label className="grid gap-1 text-xs text-ink-muted">
            Tell the agent what you want
            <textarea
              value={chatText}
              disabled={phase !== "idle"}
              onChange={(event) => setChatText(event.target.value)}
              rows={2}
              placeholder="Make it feel more tense and dangerous"
              className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-sans text-sm text-ink disabled:opacity-50"
            />
          </label>

          <button
            type="button"
            disabled={!goEnabled || phase !== "idle"}
            onClick={go}
            className="rounded-sm border border-tungsten bg-tungsten px-3 py-2 font-mono text-xs uppercase tracking-wider text-bg transition-colors ease-chrome hover:border-ink hover:bg-ink disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Go
          </button>

          {phase === "asking" && pendingQuestion ? (
            <div className="rounded-md border border-dashed border-line p-3">
              <p className="font-mono text-[11px] uppercase tracking-wider text-ink-muted">
                Question {turns.length + 1} of {MAX_CLARIFY_QUESTIONS}
              </p>
              <p className="mt-1 text-sm text-ink">{pendingQuestion}</p>
              <label className="mt-2 grid gap-1 text-xs text-ink-muted">
                Your answer
                <input
                  value={answerDraft}
                  onChange={(event) => setAnswerDraft(event.target.value)}
                  className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-sans text-sm text-ink"
                />
              </label>
              <button
                type="button"
                disabled={!answerDraft.trim()}
                onClick={() => void sendAnswer()}
                className="mt-2 rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
              >
                Send answer
              </button>
            </div>
          ) : null}

          {phase === "generating" ? (
            <p className="font-mono text-[11px] uppercase tracking-wider text-tungsten">
              Generating your new version…
            </p>
          ) : null}

          {phase === "done" && resultAlternateId ? (
            <div className="rounded-md border border-dashed border-line p-3">
              <p className="font-mono text-[11px] uppercase tracking-wider text-signal">
                New version ready: {resultAlternateId}
              </p>
              {videoUrl ? (
                <video
                  role="video"
                  src={videoUrl}
                  controls
                  preload="metadata"
                  className="mt-2 w-full rounded-sm border border-line"
                />
              ) : (
                <p className="mt-2 text-xs text-ink-muted">Loading preview…</p>
              )}
              {promoted ? (
                <p className="mt-2 font-mono text-[11px] uppercase tracking-wider text-signal">
                  Added to the final cut.
                </p>
              ) : (
                <button
                  type="button"
                  onClick={() => void addToFinalCut()}
                  className="mt-2 rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                >
                  Add to final cut
                </button>
              )}
              <button
                type="button"
                onClick={() => resetForNewClip(selectedOrigin)}
                className="ml-2 mt-2 rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink-muted hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                Start another edit on this clip
              </button>
            </div>
          ) : null}

          {error ? (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}

      {reviewClip ? (
        <ClipReviewModal clip={reviewClip} onClose={() => setReviewClip(null)} />
      ) : null}
    </section>
  );
}
