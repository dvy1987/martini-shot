import { ApiError } from "@/api/client";

interface CaseNoteProps {
  error: ApiError;
  onRetry?: () => void;
}

/** Inline error — never window.alert (Step 6). */
export default function CaseNote({ error, onRetry }: CaseNoteProps) {
  return (
    <div className="rounded-md border border-line bg-surface-1 px-5 py-4">
      <p className="text-sm text-ink">{error.message}</p>
      <p className="mt-2 font-mono text-xs uppercase tracking-wider text-ink-muted">{error.code}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-sm border border-line bg-surface-2 px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
