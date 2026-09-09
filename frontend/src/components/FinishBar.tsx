/** Upload clips, set a $50 finishing budget, walk away. */
import { useEffect, useMemo, useRef, useState } from "react";

import { getJob, ingestClip, startFinish } from "@/api/endpoints";
import { clipName } from "@/lib/clipDisplay";
import { moveItem, reorder } from "@/lib/clipOrdering";
import type { Job } from "@/types/api";

interface FinishBarProps {
  projectId: string;
  onFinished?: () => void;
  compact?: boolean;
  active?: boolean;
  existingJobs?: readonly Job[];
}

interface ClipRow {
  name: string;
  file?: File;
  job?: Job;
  skipped?: boolean;
}

const INGEST_TERMINAL = new Set<Job["status"]>([
  "pass",
  "fail",
  "quarantined",
  "needs_human",
  "throttled",
]);

function ingestJobsOf(jobs: readonly Job[]): Job[] {
  return jobs.filter((job) => job.station === "ingest");
}

function rowsFromJobs(jobs: readonly Job[]): ClipRow[] {
  return ingestJobsOf(jobs)
    .slice()
    .sort((a, b) =>
      clipName(a).localeCompare(clipName(b), undefined, { numeric: true, sensitivity: "base" }),
    )
    .map((job) => ({
      name: clipName(job),
      job,
    }));
}

function ingestLabel(status: Job["status"]): string {
  if (status === "pass") return "file checked";
  if (status === "queued") return "in bin";
  if (status === "running") return "checking";
  if (status === "quarantined") return "broken file";
  if (status === "needs_human") return "needs review";
  if (status === "throttled") return "held";
  return "failed";
}

export default function FinishBar({
  projectId,
  onFinished,
  compact = false,
  active = false,
  existingJobs = [],
}: FinishBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragFrom = useRef<number | null>(null);
  const [budget, setBudget] = useState("50");
  const [rows, setRows] = useState<ClipRow[]>(() => rowsFromJobs(existingJobs));
  const [failedNames, setFailedNames] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [showPrep, setShowPrep] = useState(!compact);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const incoming = ingestJobsOf(existingJobs);
    setRows((current) => {
      const known = new Set(current.map((row) => row.job?.job_id).filter((id): id is string => Boolean(id)));
      const byId = new Map(incoming.map((job) => [job.job_id, job]));
      let changed = false;
      const updated = current.map((row) => {
        if (!row.job) return row;
        const next = byId.get(row.job.job_id);
        if (!next || next.status === row.job.status) return row;
        changed = true;
        return { ...row, job: next };
      });
      // A clip still being uploaded has no job attached yet, but the upload
      // has already created its ingest job server-side and SSE may deliver it
      // mid-batch. Skip additions whose clip name belongs to an in-flight
      // upload — the upload response will attach that job to the existing row.
      const pendingUploadNames = new Set(
        current
          .filter((row) => row.file && !row.job && !row.skipped)
          .map((row) => row.name),
      );
      const additions = incoming.filter(
        (job) => !known.has(job.job_id) && !pendingUploadNames.has(clipName(job)),
      );
      if (!changed && additions.length === 0) return current;
      return [...updated, ...rowsFromJobs(additions)];
    });
  }, [existingJobs]);

  const remaining = useMemo(
    () => rows.filter((row) => row.file && !row.job && !row.skipped),
    [rows],
  );
  const orderedJobs = useMemo(
    () => rows.map((row) => row.job).filter((job): job is Job => job != null && job.status === "pass"),
    [rows],
  );
  const validationPending = rows.some((row) => row.job != null && !INGEST_TERMINAL.has(row.job.status));
  const sequenceValidated =
    remaining.length === 0 && !validationPending && orderedJobs.length > 0;

  function onFiles(files: FileList | null) {
    if (!files?.length) return;
    const incoming = Array.from(files).sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }),
    );
    setRows((current) => [...current, ...incoming.map((file) => ({ name: file.name, file }))]);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    void acceptFiles(incoming);
  }

  function move(index: number, delta: -1 | 1) {
    setRows((current) => reorder(current, index, delta));
  }

  function dropOn(index: number) {
    const from = dragFrom.current;
    dragFrom.current = null;
    if (from == null || started || pending) return;
    setRows((current) => moveItem(current, from, index));
  }

  function remove(index: number) {
    if (started) return;
    const row = rows[index];
    if (!row?.file) return;
    setRows((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setFailedNames((current) => current.filter((name) => name !== row.name));
  }

  function resetTurnover() {
    setRows(rowsFromJobs(existingJobs));
    setFailedNames([]);
    setError(null);
    setNote(null);
    setStarted(false);
  }

  async function waitForFileChecks(initial: ClipRow[]): Promise<ClipRow[]> {
    let current = initial;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const activeChecks = current.some((item) => item.job != null && !INGEST_TERMINAL.has(item.job.status));
      if (!activeChecks) return current;
      if (attempt > 0) {
        await new Promise((resolve) => window.setTimeout(resolve, 1_500));
      }
      current = await Promise.all(
        current.map(async (item) =>
          item.job == null || INGEST_TERMINAL.has(item.job.status)
            ? item
            : { ...item, job: await getJob(item.job.job_id) },
        ),
      );
      setRows((rowsNow) =>
        rowsNow.map((row) => {
          const match = current.find((item) => item.file === row.file || item.job?.job_id === row.job?.job_id);
          return match?.job ? { ...row, job: match.job } : row;
        }),
      );
    }
    throw new Error("File validation is still running. Check again before starting the lab.");
  }

  async function acceptFiles(incoming: File[]) {
    setError(null);
    setPending(true);
    const accepted: ClipRow[] = [];
    const rejected: string[] = [];
    try {
      for (const file of incoming) {
        try {
          const nextJob = await ingestClip(projectId, file);
          const row = { name: file.name, file, job: nextJob };
          accepted.push(row);
          setRows((current) => current.map((item) => (item.file === file ? row : item)));
        } catch {
          rejected.push(file.name);
          setRows((current) =>
            current.map((item) => (item.file === file ? { ...item, skipped: true } : item)),
          );
        }
      }
      const checked = accepted.length > 0 ? await waitForFileChecks(accepted) : accepted;
      for (const item of checked) {
        if (item.job?.status !== "pass" && !rejected.includes(item.name)) {
          rejected.push(item.name);
        }
      }
      setFailedNames(rejected);
      const passed = checked.filter((item) => item.job?.status === "pass");
      if (passed.length > 0) {
        setNote(`${passed.length} clip${passed.length === 1 ? "" : "s"} uploaded`);
        onFinished?.();
      }
    } finally {
      setPending(false);
    }
  }

  async function onCheckValidation() {
    setError(null);
    setPending(true);
    try {
      const pendingRows = rows.filter((row) => row.job != null && !INGEST_TERMINAL.has(row.job.status));
      const checked = await waitForFileChecks(pendingRows);
      const rejected = checked
        .filter((item) => item.job?.status !== "pass")
        .map((item) => item.name);
      setFailedNames(rejected);
      const passed = checked.filter((item) => item.job?.status === "pass");
      if (passed.length > 0) {
        setNote(`${passed.length} clip${passed.length === 1 ? "" : "s"} uploaded`);
      }
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
      // The API requires unique ingest_job_ids (backend 409s otherwise).
      await startFinish(projectId, micros, [
        ...new Set(orderedJobs.map((item) => item.job_id)),
      ]);
      setStarted(true);
      setNote("Wrap has been called");
      onFinished?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not call wrap");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mb-6 overflow-hidden rounded-md border border-line bg-surface-1">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-2 px-5 py-4">
        <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-tungsten">Step 1: Choose your clips</p>
        <h2 className="mt-1 text-xl text-ink">{compact && !showPrep ? "Wrap is in progress" : "Upload clips and set a budget"}</h2>
        {compact && !showPrep ? <p className="mt-1 text-sm text-ink-muted">{active ? "Wrap has already been called. Start a new run after this one finishes." : "The last run is complete. Call wrap again when you are ready."}</p> : <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">Clips are accepted in the order you choose them. After they are in, drag a row to change the order.</p>}
        </div>
        {compact && !active ? <button type="button" onClick={() => setShowPrep((open) => !open)} className="border border-line px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:border-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">{showPrep ? "Hide setup" : "Call wrap again"}</button> : null}
      </header>
      {showPrep ? <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1fr_18rem]">
        <div>
          <div className="grid gap-2">
            <input
              id="turnover-clips"
              ref={fileInputRef}
              type="file"
              accept=".mp4,.mov,.m4v,.webm,.wav,.mp3,.m4a,video/mp4,video/quicktime,video/*,audio/*"
              multiple
              disabled={pending || started}
              aria-label="Upload media"
              onChange={(event) => onFiles(event.target.files)}
              className="sr-only"
            />
            <button
              type="button"
              disabled={pending || started}
              onClick={() => fileInputRef.current?.click()}
              className="w-fit rounded-sm border border-line bg-surface-2 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              Upload media
            </button>
            <p className="text-xs leading-relaxed text-ink-muted">
              Choose one or more clips. They are accepted immediately, in that order. Drag a clip up or down if you need a different sequence.
            </p>
          </div>
          <ol className="mt-4 space-y-2" aria-label="Ordered clips">
            {rows.length === 0 ? <li className="border border-dashed border-line px-4 py-5 font-mono text-xs text-ink-muted">No clips added yet. Upload media to accept them in order.</li> : rows.map((row, index) => (
              <li
                key={`${row.job?.job_id ?? row.name}-${index}`}
                draggable={!pending && !started}
                aria-label={`Clip ${index + 1}: ${row.name}`}
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
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{row.name}</span>
                {row.job ? (
                  <span className={`font-mono text-[10px] uppercase ${row.job.status === "pass" ? "text-signal" : "text-tungsten"}`}>
                    {ingestLabel(row.job.status)}
                  </span>
                ) : row.skipped ? (
                  <span className="font-mono text-[10px] uppercase text-danger">could not upload</span>
                ) : (
                  <span className="font-mono text-[10px] uppercase text-tungsten">uploading</span>
                )}
                <span className="flex gap-1">
                  <button type="button" aria-label={`Move ${row.name} up`} disabled={pending || started || index === 0} onClick={() => move(index, -1)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-ink-muted disabled:opacity-30">Up</button>
                  <button type="button" aria-label={`Move ${row.name} down`} disabled={pending || started || index === rows.length - 1} onClick={() => move(index, 1)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-ink-muted disabled:opacity-30">Down</button>
                  {row.file ? (
                    <button type="button" aria-label={`Remove ${row.name}`} disabled={pending || started} onClick={() => remove(index)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-danger disabled:opacity-30">Remove</button>
                  ) : null}
                </span>
              </li>
            ))}
          </ol>
          {failedNames.length > 0 ? (
            <p className="mt-3 border-l-2 border-danger px-3 py-2 text-sm text-danger">
              Could not upload {failedNames.map((name) => `“${name}”`).join(", ")}.
              {orderedJobs.length > 0 ? " The other clips were still sent." : ""}
            </p>
          ) : null}
          {rows.length > 0 && !pending ? <button type="button" onClick={resetTurnover} className="mt-3 border-b border-line pb-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">Start over</button> : null}
        </div>
        <div className="border-l border-line pl-5">
          <label className="grid gap-2 font-mono text-xs uppercase tracking-wider text-ink-muted">Budget
            <div className="flex items-center gap-2"><span className="text-ink">$</span><input type="number" min={1} value={budget} onChange={(event) => setBudget(event.target.value)} className="w-full rounded-sm border border-line bg-surface-2 px-3 py-2 font-mono text-sm text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten" /></div>
          </label>
          <p className="mt-3 text-xs leading-relaxed text-ink-muted">Martini Shot will choose the highest-impact improvements that fit this budget. Basic audio and picture checks run first.</p>
          <button
            type="button"
            disabled={pending || started || active || !sequenceValidated}
            aria-describedby={!sequenceValidated && !pending && !started && !active ? "call-wrap-hint" : undefined}
            title={
              pending
                ? "Working…"
                : started || active
                  ? "Wrap has already been called"
                  : sequenceValidated
                    ? "Call wrap to start finishing"
                    : "Call wrap after every chosen clip has been checked"
            }
            onClick={() => void onFinish()}
            className="mt-5 w-full rounded-sm border border-tungsten bg-tungsten px-4 py-3 font-mono text-xs uppercase tracking-wider text-bg shadow-[0_1px_0_rgba(0,0,0,0.25)] transition-[transform,box-shadow,filter,opacity] duration-150 ease-chrome hover:-translate-y-px hover:shadow-[var(--shadow-lift)] hover:brightness-110 active:translate-y-0 active:scale-[0.98] active:shadow-none active:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tungsten focus-visible:ring-offset-2 focus-visible:ring-offset-bg enabled:cursor-pointer disabled:cursor-not-allowed disabled:translate-y-0 disabled:scale-100 disabled:opacity-40 disabled:shadow-none disabled:brightness-100 disabled:hover:translate-y-0 disabled:hover:shadow-none disabled:hover:brightness-100"
          >
            {pending ? "Working…" : started ? "Wrap has been called" : "Call Wrap"}
          </button>
          {!sequenceValidated && !pending && !started && !active ? (
            <p id="call-wrap-hint" className="mt-2 text-xs leading-relaxed text-ink-muted">
              Call wrap after every chosen clip has been checked.
            </p>
          ) : null}
          {validationPending ? <button type="button" disabled={pending} onClick={() => void onCheckValidation()} className="mt-2 w-full rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted enabled:cursor-pointer disabled:cursor-not-allowed disabled:opacity-40">{pending ? "Checking files…" : "Check file status"}</button> : null}
        </div>
      </div> : null}
      <div className="border-t border-line px-5 py-3">
        {note ? <p role="status" className="font-mono text-xs text-signal">{note}</p> : null}
        {error ? <p role="alert" className="font-mono text-xs text-danger">{error}</p> : null}
      </div>
    </section>
  );
}
