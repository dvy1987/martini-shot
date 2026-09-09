import { useEffect, useState } from "react";

import { ApiError, mediaUrl } from "@/api/client";
import { getJobClip } from "@/api/endpoints";
import type { JobClip } from "@/types/api";

function labMediaClip(jobId: string, side: "before" | "after", label: string): JobClip {
  return {
    job_id: jobId,
    side,
    clip_name: label,
    url: `/api/v1/jobs/${encodeURIComponent(jobId)}/clip/${side}/media`,
    expires_in_minutes: 60,
    metadata: {},
  };
}

interface ClipThumbProps {
  jobId: string;
  side: "before" | "after";
  label: string;
  onOpen: (clip: JobClip) => void;
  reviewSide?: "before" | "after";
}

export default function ClipThumb({ jobId, side, label, onOpen, reviewSide }: ClipThumbProps) {
  const [clip, setClip] = useState<JobClip | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getJobClip(jobId, side)
      .then((next) => {
        if (!cancelled) setClip(next);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 502) {
          setClip(labMediaClip(jobId, side, label));
          return;
        }
        setError(err instanceof Error ? err.message : "The clip could not be opened.");
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, side]);

  if (error) {
    return <p className="text-xs text-danger">{error}</p>;
  }
  if (!clip) {
    return <p className="font-mono text-[10px] uppercase text-ink-muted">Opening clip…</p>;
  }

  return (
    <button
      type="button"
      aria-label={`Open ${label}`}
      onClick={() => onOpen({ ...clip, side: reviewSide ?? clip.side })}
      className="block w-28 cursor-pointer overflow-hidden rounded-sm border border-line bg-surface-2 text-left transition-[border-color,transform] ease-chrome hover:-translate-y-px hover:border-tungsten focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten active:translate-y-0 active:scale-[0.98]"
    >
      <video src={mediaUrl(clip.url)} muted preload="none" className="aspect-video w-full object-cover" />
      <span className="block truncate px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
        {label}
      </span>
    </button>
  );
}
