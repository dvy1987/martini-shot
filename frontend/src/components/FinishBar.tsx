/** Upload clips, set a $50 finishing budget, walk away. */
import { useMemo, useRef, useState } from "react";

import { getJob, ingestClip, startFinish } from "@/api/endpoints";
import { moveItem, reorder } from "@/lib/clipOrdering";
import type { Job } from "@/types/api";

interface FinishBarProps {
  projectId: string;
  onFinished?: () => void;
  compact?: boolean;
  active?: boolean;
}

interface UploadedClip {
  file: File;
  job: Job;
}

const INGEST_TERMINAL = new Set<Job["status"]>([
  "pass",
  "fail",
  "quarantined",
  "needs_human",
  "throttled",
]);

function ingestLabel(status: Job["status"]): string {
  if (status === "pass") return "file checked";
  if (status === "queued") return "in bin";
  if (status === "running") return "checking";
  if (status === "quarantined") return "broken file";
  if (status === "needs_human") return "needs review";
  if (status === "throttled") return "held";
  return "failed";
}

export default function FinishBar({ projectId, onFinished, compact = false, active = false }: FinishBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragFrom = useRef<number | null>(null);
  const [budget, setBudget] = useState("50");
  const [staged, setStaged] = useState<File[]>([]);
  const [uploaded, setUploaded] = useState<UploadedClip[]>([]);
  const [failed, setFailed] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [showPrep, setShowPrep] = useState(!compact);
  const [started, setStarted] = useState(false);

  const remaining = useMemo(
    () => staged.filter((file) => !uploaded.some((item) => item.file === file)),
    [staged, uploaded],
  );
  const orderedJobs = useMemo(
    () =>
      staged
        .map((file) => uploaded.find((item) => item.file === file)?.job)
        .filter((job): job is Job => job != null),
    [staged, uploaded],
  );
  const sequenceValidated =
    staged.length > 0 &&
    remaining.length === 0 &&
    orderedJobs.length === staged.length &&
    orderedJobs.every((job) => job.status === "pass");
  const validationPending =
    remaining.length === 0 &&
    uploaded.some((item) => !INGEST_TERMINAL.has(item.job.status));

  function onFiles(files: FileList | null) {
    if (!files?.length) return;
    const incoming = Array.from(files);
    setStaged((current) => [...current, ...incoming]);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    void acceptFiles(incoming);
  }

  function move(index: number, delta: -1 | 1) {
    setStaged((current) => reorder(current, index, delta));
  }

  function dropOn(index: number) {
    const from = dragFrom.current;
    dragFrom.current = null;
    if (from == null || started || pending) return;
    setStaged((current) => moveItem(current, from, index));
  }

  function remove(file: File) {
    if (started) return;
    setStaged((current) => current.filter((item) => item !== file));
    setUploaded((current) => current.filter((item) => item.file !== file));
  }

  function resetTurnover() {
    setStaged([]);
    setUploaded([]);
    setFailed(null);
    setError(null);
    setNote(null);
    setStarted(false);
  }

  async function waitForFileChecks(initial: UploadedClip[]): Promise<UploadedClip[]> {
    let current = initial;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const active = current.some((item) => !INGEST_TERMINAL.has(item.job.status));
      if (!active) return current;
      if (attempt > 0) {
        await new Promise((resolve) => window.setTimeout(resolve, 1_500));
      }
      current = await Promise.all(
        current.map(async (item) =>
          INGEST_TERMINAL.has(item.job.status)
            ? item
            : { ...item, job: await getJob(item.job.job_id) },
        ),
      );
      setUploaded(current);
    }
    throw new Error("File validation is still running. Check again before starting the lab.");
  }

  async function acceptFiles(incoming: File[]) {
    setError(null);
    setFailed(null);
    setPending(true);
    try {
      const accepted = [...uploaded];
      for (const file of incoming) {
        try {
          const nextJob = await ingestClip(projectId, file);
          accepted.push({ file, job: nextJob });
          setUploaded([...accepted]);
        } catch (err) {
          setFailed(file.name);
          throw err;
        }
      }
      const checked = await waitForFileChecks(accepted);
      const stopped = checked.find((item) => item.job.status !== "pass");
      if (stopped) {
        setFailed(stopped.file.name);
        setError(`${stopped.file.name} did not pass file validation.`);
        return;
      }
      setNote(`${checked.length} clip${checked.length === 1 ? "" : "s"} accepted`);
      onFinished?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setPending(false);
    }
  }

  async function onCheckValidation() {
    setError(null);
    setPending(true);
    try {
      const checked = await waitForFileChecks(uploaded);
      const stopped = checked.find((item) => item.job.status !== "pass");
      if (stopped) {
        setFailed(stopped.file.name);
        setError(
          `${stopped.file.name} did not pass file validation. Start over to choose a new sequence.`,
        );
        return;
      }
      setFailed(null);
      setNote(`${checked.length} clip${checked.length === 1 ? "" : "s"} accepted`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "File validation could not be checked.");
    } finally {
      setPending(false);
    }
  }

  async function onFinish() {
    setError(null);
    setPending(true);
    try {
      const dollars = Number(budget);
      if (!Number.isFinite(dollars) || dollars <= 0) {
        setError("Enter a finite budget greater than zero.");
        return;
      }
      const micros = Math.round(dollars * 1_000_000);
      await startFinish(
        projectId,
        micros,
        orderedJobs.map((item) => item.job_id),
      );
      setStarted(true);
      setNote("Finishing has started");
      onFinished?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Finish failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mb-6 overflow-hidden rounded-md border border-line bg-surface-1">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-2 px-5 py-4">
        <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-tungsten">Step 1: Choose your clips</p>
        <h2 className="mt-1 text-xl text-ink">{compact && !showPrep ? "Finishing is in progress" : "Upload clips and set a budget"}</h2>
        {compact && !showPrep ? <p className="mt-1 text-sm text-ink-muted">{active ? "A finishing run is already in progress. Start a new run after it finishes." : "The last run is complete. Start a new run when you are ready."}</p> : <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">Clips are accepted in the order you choose them. After they are in, drag a row to change the order.</p>}
        </div>
        {compact && !active ? <button type="button" onClick={() => setShowPrep((open) => !open)} className="border border-line px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:border-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">{showPrep ? "Hide setup" : "Start a new finishing run"}</button> : null}
      </header>
      {showPrep ? <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1fr_18rem]">
        <div>
          <div className="grid gap-2">
            <p className="font-mono text-xs uppercase tracking-wider text-ink-muted">Choose files</p>
            <input
              id="turnover-clips"
              ref={fileInputRef}
              type="file"
              accept=".mp4,.mov,.m4v,.webm,.wav,.mp3,.m4a,video/mp4,video/quicktime,video/*,audio/*"
              multiple
              disabled={pending || started}
              aria-label="Choose files"
              onChange={(event) => onFiles(event.target.files)}
              className="sr-only"
            />
            <button
              type="button"
              disabled={pending || started}
              onClick={() => fileInputRef.current?.click()}
              className="w-fit rounded-sm border border-line bg-surface-2 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              Choose files
            </button>
            <p className="text-xs leading-relaxed text-ink-muted">
              Choose one or more clips. They are accepted immediately, in that order. Drag a clip up or down if you need a different sequence.
            </p>
          </div>
          <ol className="mt-4 space-y-2" aria-label="Ordered clips">
            {staged.length === 0 ? <li className="border border-dashed border-line px-4 py-5 font-mono text-xs text-ink-muted">No clips added yet. Choose files to accept them in order.</li> : staged.map((file, index) => (
              <li
                key={`${file.name}-${index}`}
                draggable={!pending && !started}
                aria-label={`Clip ${index + 1}: ${file.name}`}
                onDragStart={() => {
                  dragFrom.current = index;
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  dropOn(index);
                }}
                className={`flex items-center gap-3 border border-line bg-surface-2 px-3 py-2 ${pending || started ? "" : "cursor-grab"}`}
              >
                <span className="w-5 font-mono text-xs text-tungsten">{String(index + 1).padStart(2, "0")}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{file.name}</span>
                {uploaded.find((item) => item.file === file) ? (
                  <span className={`font-mono text-[10px] uppercase ${uploaded.find((item) => item.file === file)?.job.status === "pass" ? "text-signal" : "text-tungsten"}`}>
                    {ingestLabel(uploaded.find((item) => item.file === file)?.job.status ?? "queued")}
                  </span>
                ) : (
                  <span className="font-mono text-[10px] uppercase text-tungsten">accepting</span>
                )}
                <span className="flex gap-1">
                  <button type="button" aria-label={`Move ${file.name} up`} disabled={pending || started || index === 0} onClick={() => move(index, -1)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-ink-muted disabled:opacity-30">Up</button>
                  <button type="button" aria-label={`Move ${file.name} down`} disabled={pending || started || index === staged.length - 1} onClick={() => move(index, 1)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-ink-muted disabled:opacity-30">Down</button>
                  <button type="button" aria-label={`Remove ${file.name}`} disabled={pending || started} onClick={() => remove(file)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-danger disabled:opacity-30">Remove</button>
                </span>
              </li>
            ))}
          </ol>
          {failed ? <p className="mt-3 border-l-2 border-danger px-3 py-2 text-sm text-danger">Upload stopped at “{failed}”. The remaining clips were not uploaded and the finishing run was not started.</p> : null}
          {uploaded.length > 0 && !pending ? <button type="button" onClick={resetTurnover} className="mt-3 border-b border-line pb-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">Start over</button> : null}
        </div>
        <div className="border-l border-line pl-5">
          <label className="grid gap-2 font-mono text-xs uppercase tracking-wider text-ink-muted">Budget
            <div className="flex items-center gap-2"><span className="text-ink">$</span><input type="number" min={1} value={budget} onChange={(event) => setBudget(event.target.value)} className="w-full rounded-sm border border-line bg-surface-2 px-3 py-2 font-mono text-sm text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten" /></div>
          </label>
          <p className="mt-3 text-xs leading-relaxed text-ink-muted">Martini Shot will choose the highest-priority improvements that fit this budget. Basic audio and picture checks run first.</p>
          <button type="button" disabled={pending || started || active || !sequenceValidated} onClick={() => void onFinish()} className="mt-5 w-full rounded-sm border border-tungsten bg-tungsten px-4 py-3 font-mono text-xs uppercase tracking-wider text-bg transition-opacity hover:opacity-90 disabled:opacity-40">{pending ? "Working…" : started ? "Finishing has started" : "Start finishing"}</button>
          {validationPending ? <button type="button" disabled={pending} onClick={() => void onCheckValidation()} className="mt-2 w-full rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink hover:border-ink-muted disabled:opacity-40">{pending ? "Checking files…" : "Check file status"}</button> : null}
        </div>
      </div> : null}
      <div className="border-t border-line px-5 py-3">
        {note ? <p role="status" className="font-mono text-xs text-signal">{note}</p> : null}
        {error ? <p role="alert" className="font-mono text-xs text-danger">{error}</p> : null}
      </div>
    </section>
  );
}
