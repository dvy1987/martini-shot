import { useEffect } from "react";

import { mediaUrl } from "@/api/client";
import type { JobClip } from "@/types/api";

interface ClipReviewModalProps {
  clip: JobClip;
  onClose: () => void;
}

function asText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function technicalRows(metadata: Record<string, unknown>): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  const labels: Record<string, string> = {
    duration_s: "Duration",
    fps: "Frame rate",
    codec: "Codec",
    has_audio: "Audio",
    width: "Width",
    height: "Height",
  };
  for (const [key, label] of Object.entries(labels)) {
    const value = metadata[key];
    if (value == null || value === "") continue;
    if (typeof value === "boolean") rows.push([label, value ? "Yes" : "No"]);
    else rows.push([label, String(value)]);
  }
  return rows;
}

export default function ClipReviewModal({ clip, onClose }: ClipReviewModalProps) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const scene = asText(clip.metadata.scene);
  const spoken = asText(clip.metadata.spoken_words);
  const rows = technicalRows(clip.metadata);
  const hasNotes = Boolean(scene || spoken || rows.length);

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-bg/80 px-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="clip-review-title"
        className="w-full max-w-3xl rounded-md border border-line bg-surface-1 p-5"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-ink-muted">
              {clip.side === "before" ? "Before this step" : "After this step"}
            </p>
            <h2 id="clip-review-title" className="mt-1 text-lg text-ink">
              {clip.clip_name}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-line px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted transition-colors ease-chrome hover:border-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Close
          </button>
        </div>
        <div className="relative mt-4">
          <video
            role="video"
            src={mediaUrl(clip.url)}
            controls
            autoPlay
            className="w-full rounded-sm border border-line bg-bg"
          />
          {spoken ? (
            <p
              aria-label="Subtitles"
              className="pointer-events-none absolute inset-x-4 bottom-12 max-h-24 overflow-y-auto rounded-sm bg-bg/80 px-3 py-2 text-center text-sm leading-relaxed text-ink"
            >
              {spoken}
            </p>
          ) : null}
        </div>
        {scene ? (
          <section className="mt-4">
            <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Scene</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink">{scene}</p>
          </section>
        ) : null}
        {rows.length > 0 ? (
          <dl className="mt-4 grid gap-2 sm:grid-cols-2">
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                  {label}
                </dt>
                <dd className="mt-1 text-sm text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {!hasNotes ? (
          <p className="mt-4 text-sm text-ink-muted">No extra notes are attached to this clip yet.</p>
        ) : null}
      </div>
    </div>
  );
}
