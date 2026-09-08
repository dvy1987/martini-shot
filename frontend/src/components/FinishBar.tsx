/** Upload clips, set a $50 finishing budget, walk away. */
import { useMemo, useState } from "react";

import { getJob, ingestClip, startFinish } from "@/api/endpoints";
import { reorder } from "@/lib/clipOrdering";
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
  const sequenceValidated =
    staged.length > 0 &&
    remaining.length === 0 &&
    uploaded.length === staged.length &&
    uploaded.every((item) => item.job.status === "pass");
  const validationPending =
    remaining.length === 0 &&
    uploaded.some((item) => !INGEST_TERMINAL.has(item.job.status));

  function onFiles(files: FileList | null) {
    if (!files?.length) return;
    setStaged((current) => [...current, ...Array.from(files)]);
    setError(null);
  }

  function move(index: number, delta: -1 | 1) {
    setStaged((current) => reorder(current, index, delta));
  }

  function remove(file: File) {
    if (uploaded.some((item) => item.file === file)) return;
    setStaged((current) => current.filter((item) => item !== file));
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

  async function onStart() {
    setError(null);
    setFailed(null);
    setPending(true);
    try {
      const accepted = [...uploaded];
      for (const file of remaining) {
        try {
          const job = await ingestClip(projectId, file);
          accepted.push({ file, job });
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
        setError(
          `${stopped.file.name} did not pass file validation. The finishing run was not started.`,
        );
        return;
      }
      setNote(`${staged.length} clip${staged.length === 1 ? "" : "s"} checked in order`);
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
          `${stopped.file.name} did not pass file validation. Reset the turnover to choose a new sequence.`,
        );
        return;
      }
      setFailed(null);
      setNote(`${checked.length} clip${checked.length === 1 ? "" : "s"} checked in order`);
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
      await startFinish(projectId, micros, uploaded.map((item) => item.job.job_id));
      setStarted(true);
      setNote("Finishing started");
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
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-tungsten">01 / turnover brief</p>
        <h2 className="mt-1 text-xl text-ink">{compact && !showPrep ? "Turnover is in the lab" : "Set the order. Set the envelope."}</h2>
        {compact && !showPrep ? <p className="mt-1 text-sm text-ink-muted">{active ? "The active run owns the screen. A new turnover can begin after this one stops." : "The last run is on record. Start another turnover when you are ready."}</p> : <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">The lab will work through your clips in this order. It checks originals first, then mixes and repairs every clip before it considers optional finishing work.</p>}
        </div>
        {compact && !active ? <button type="button" onClick={() => setShowPrep((open) => !open)} className="border border-line px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:border-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">{showPrep ? "Hide turnover setup" : "Start another turnover"}</button> : null}
      </header>
      {showPrep ? <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1fr_18rem]">
        <div>
          <label className="grid gap-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
            <span>Upload clips <span className="sr-only">(staged in order)</span></span>
            <input type="file" accept="video/*,audio/*" multiple disabled={pending} onChange={(event) => onFiles(event.target.files)} className="w-full text-sm normal-case tracking-normal text-ink file:mr-3 file:rounded-sm file:border file:border-line file:bg-surface-2 file:px-3 file:py-2 file:font-mono file:text-[10px] file:uppercase file:tracking-wider file:text-ink" />
          </label>
          <ol className="mt-4 space-y-2" aria-label="Ordered clips">
            {staged.length === 0 ? <li className="border border-dashed border-line px-4 py-5 font-mono text-xs text-ink-muted">No clips staged yet. The order you choose becomes the upload order.</li> : staged.map((file, index) => (
              <li key={`${file.name}-${index}`} className="flex items-center gap-3 border border-line bg-surface-2 px-3 py-2">
                <span className="w-5 font-mono text-xs text-tungsten">{String(index + 1).padStart(2, "0")}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{file.name}</span>
                {uploaded.find((item) => item.file === file) ? (
                  <span className={`font-mono text-[10px] uppercase ${uploaded.find((item) => item.file === file)?.job.status === "pass" ? "text-signal" : "text-tungsten"}`}>
                    {ingestLabel(uploaded.find((item) => item.file === file)?.job.status ?? "queued")}
                  </span>
                ) : <span className="flex gap-1"><button type="button" aria-label={`Move ${file.name} up`} disabled={pending || uploaded.length > 0 || index === 0} onClick={() => move(index, -1)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-ink-muted disabled:opacity-30">Up</button><button type="button" aria-label={`Move ${file.name} down`} disabled={pending || uploaded.length > 0 || index === staged.length - 1} onClick={() => move(index, 1)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-ink-muted disabled:opacity-30">Down</button><button type="button" aria-label={`Remove ${file.name}`} disabled={pending || uploaded.length > 0} onClick={() => remove(file)} className="border border-line px-2 py-1 font-mono text-[10px] uppercase text-danger disabled:opacity-30">Remove</button></span>}
              </li>
            ))}
          </ol>
          {uploaded.length > 0 ? <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted">Sequence locked after the first accepted upload.</p> : null}
          {failed ? <p className="mt-3 border-l-2 border-danger px-3 py-2 text-sm text-danger">Upload stopped at “{failed}”. Later clips were not sent and no downstream work is implied.</p> : null}
          {uploaded.length > 0 && !pending ? <button type="button" onClick={resetTurnover} className="mt-3 border-b border-line pb-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten">Reset turnover</button> : null}
        </div>
        <div className="border-l border-line pl-5">
          <label className="grid gap-2 font-mono text-xs uppercase tracking-wider text-ink-muted">Finishing envelope
            <div className="flex items-center gap-2"><span className="text-ink">$</span><input type="number" min={1} value={budget} onChange={(event) => setBudget(event.target.value)} className="w-full rounded-sm border border-line bg-surface-2 px-3 py-2 font-mono text-sm text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten" /></div>
          </label>
          <p className="mt-3 text-xs leading-relaxed text-ink-muted">The orchestrator may leave proposed work out when the real estimates exceed this limit.</p>
          <button type="button" disabled={pending || started || active || !sequenceValidated} onClick={() => void onFinish()} className="mt-5 w-full rounded-sm border border-tungsten bg-tungsten px-4 py-3 font-mono text-xs uppercase tracking-wider text-bg transition-opacity hover:opacity-90 disabled:opacity-40">{pending ? "Working…" : started ? "Finishing started" : "Finish / start the lab"}</button>
          {staged.length > 0 && remaining.length > 0 ? <button type="button" disabled={pending} onClick={() => void onStart()} className="mt-2 w-full rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink hover:border-ink-muted disabled:opacity-40">{pending ? "Uploading in order…" : `Upload ${remaining.length} clip${remaining.length === 1 ? "" : "s"} in order`}</button> : null}
          {validationPending ? <button type="button" disabled={pending} onClick={() => void onCheckValidation()} className="mt-2 w-full rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink hover:border-ink-muted disabled:opacity-40">{pending ? "Checking files…" : "Check file validation"}</button> : null}
        </div>
      </div> : null}
      <div className="border-t border-line px-5 py-3">
        {note ? <p role="status" className="font-mono text-xs text-signal">{note}</p> : null}
        {error ? <p role="alert" className="font-mono text-xs text-danger">{error}</p> : null}
      </div>
    </section>
  );
}
