/** Upload clips, set a $50 finishing budget, walk away. */
import { useState } from "react";

import { ingestClip, startFinish } from "@/api/endpoints";

interface FinishBarProps {
  projectId: string;
  onFinished?: () => void;
}

export default function FinishBar({ projectId, onFinished }: FinishBarProps) {
  const [budget, setBudget] = useState("50");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function onFiles(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    setPending(true);
    try {
      for (const file of Array.from(files)) {
        await ingestClip(projectId, file);
      }
      setNote(`${files.length} clip${files.length === 1 ? "" : "s"} accepted`);
      onFinished?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setPending(false);
    }
  }

  async function onFinish() {
    setError(null);
    setPending(true);
    try {
      const dollars = Number(budget);
      const micros = Number.isFinite(dollars) ? Math.round(dollars * 1_000_000) : 50_000_000;
      await startFinish(projectId, micros);
      setNote("Finishing started");
      onFinished?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Finish failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mb-5 flex flex-wrap items-end gap-4 rounded-md border border-line bg-surface-1 px-4 py-3">
      <label className="grid gap-1 font-mono text-xs uppercase tracking-wider text-ink-muted">
        Upload clips
        <input
          type="file"
          accept="video/*,audio/*"
          multiple
          disabled={pending}
          onChange={(event) => void onFiles(event.target.files)}
          className="max-w-56 text-sm normal-case tracking-normal text-ink file:mr-3 file:rounded-sm file:border file:border-line file:bg-surface-2 file:px-2 file:py-1 file:font-mono file:text-[10px] file:uppercase file:tracking-wider"
        />
      </label>
      <label className="grid gap-1 font-mono text-xs uppercase tracking-wider text-ink-muted">
        Budget USD
        <input
          type="number"
          min={1}
          value={budget}
          onChange={(event) => setBudget(event.target.value)}
          className="w-24 rounded-sm border border-line bg-surface-2 px-3 py-2 font-sans text-sm normal-case tracking-normal text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
        />
      </label>
      <button
        type="button"
        disabled={pending}
        onClick={() => void onFinish()}
        className="rounded-sm border border-line bg-surface-2 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted active:bg-surface-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:opacity-50"
      >
        Finish
      </button>
      <p className="basis-full font-mono text-[10px] uppercase tracking-wider text-ink-muted">
        Upload, set a budget, Finish, walk away. Stations look; work runs in rank order until
        the money is gone.
      </p>
      {note ? <p className="font-mono text-xs text-ink-muted">{note}</p> : null}
      {error ? <p className="font-mono text-xs text-signal">{error}</p> : null}
    </div>
  );
}
