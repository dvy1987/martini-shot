import { useState } from "react";

import { getAlternateMedia } from "@/api/endpoints";
import CorrectionsControls from "@/components/CorrectionsControls";
import ExtendControls from "@/components/ExtendControls";
import type { Alternate, ShotRow } from "@/types/api";

interface AlternatesLaneProps {
  shots: ShotRow[];
  fetchMediaUrl?: (alternateId: string) => Promise<string>;
}

const ALTERNATE_STATUS_META: Record<
  string,
  { label: string; className: string }
> = {
  draft: { label: "DRAFT", className: "border-tungsten/60 text-tungsten" },
  continuity: {
    label: "In continuity",
    className: "border-signal/60 text-signal",
  },
  retired: { label: "Retired", className: "border-line text-ink-muted" },
};

function AlternateStatusChip({ status }: { status: Alternate["status"] }) {
  const meta =
    (status ? ALTERNATE_STATUS_META[status] : undefined) ??
    (status
      ? { label: status, className: "border-line text-ink-muted" }
      : { label: "Unrated", className: "border-line text-ink-muted" });
  return (
    <span
      className={`rounded-sm border px-1.5 py-0.5 font-mono text-[11px] uppercase tracking-wider ${meta.className}`}
    >
      {meta.label}
    </span>
  );
}

function AlternateCard({
  alternate,
  isCurrent,
  fetchMediaUrl,
}: {
  alternate: Alternate;
  isCurrent: boolean;
  fetchMediaUrl: (alternateId: string) => Promise<string>;
}) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const flicker = alternate.eval_scores?.flicker;

  const play = async () => {
    setIsLoading(true);
    setPlayError(null);
    try {
      setVideoUrl(await fetchMediaUrl(alternate.alternate_id));
    } catch (error) {
      setPlayError(
        error instanceof Error ? error.message : "Signed media unavailable.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      data-alternate-card=""
      data-current={isCurrent ? "true" : "false"}
      className="rounded-md border border-dashed border-line bg-surface-2/60 p-3"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-mono text-xs text-ink">{alternate.alternate_id}</span>
        <AlternateStatusChip status={alternate.status} />
        {alternate.op ? (
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-muted">
            {alternate.op}
          </span>
        ) : null}
        {flicker !== undefined ? (
          <span className="font-mono text-[11px] text-ink-muted">
            flicker <span className="text-ink">{flicker.toFixed(5)}</span>
          </span>
        ) : null}
        {alternate.tier ? (
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-muted">
            {alternate.tier}
          </span>
        ) : null}
        {alternate.artifact_ref ? (
          <button
            type="button"
            onClick={() => void play()}
            className="ml-auto rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted hover:text-tungsten focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            {isLoading ? "Signing…" : `Play ${alternate.alternate_id}`}
          </button>
        ) : null}
      </div>
      {playError ? (
        <p className="mt-2 text-sm text-danger" role="alert">
          Playback unavailable. {playError}
        </p>
      ) : null}
      {videoUrl ? (
        <video
          role="video"
          src={videoUrl}
          controls
          preload="metadata"
          className="mt-2 w-full rounded-sm border border-line"
        />
      ) : null}
    </div>
  );
}

function ShotCard({
  shot,
  fetchMediaUrl,
}: {
  shot: ShotRow;
  fetchMediaUrl: (alternateId: string) => Promise<string>;
}) {
  const count = shot.alternates.length;

  return (
    <li
      data-shot-card=""
      data-locked={shot.locked ? "true" : "false"}
      className="rounded-md border border-line bg-surface-1 p-4"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm text-ink">{shot.title ?? shot.shot_id}</h3>
        <span
          className={`font-mono text-[11px] uppercase tracking-wider ${
            shot.locked ? "text-signal" : "text-ink-muted"
          }`}
        >
          {shot.locked ? "◼ Locked" : "◇ Open"}
        </span>
        <span className="ml-auto font-mono text-[11px] uppercase tracking-wider text-ink-muted">
          {count > 0
            ? `${count} alternate${count === 1 ? "" : "s"}`
            : "No alternates yet"}
        </span>
      </div>
      {count > 0 ? (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-ink-muted">
            Generated clips live here as alternates; the locked cut is never
            silently replaced. Promotions run through Approvals.
          </p>
          {shot.alternates.map((alternate) => (
            <AlternateCard
              key={alternate.alternate_id}
              alternate={alternate}
              isCurrent={alternate.alternate_id === shot.current_alternate_id}
              fetchMediaUrl={fetchMediaUrl}
            />
          ))}
        </div>
      ) : null}
      <ExtendControls shot={shot} />
      <CorrectionsControls shot={shot} />
    </li>
  );
}

export default function AlternatesLane({
  shots,
  fetchMediaUrl,
}: AlternatesLaneProps) {
  const resolveMedia =
    fetchMediaUrl ??
    ((alternateId: string) =>
      getAlternateMedia(alternateId).then((media) => media.url));

  return (
    <section
      aria-labelledby="alternates-lane-heading"
      className="mt-8 rounded-md border border-line bg-surface-1 p-4"
    >
      <div className="flex items-baseline justify-between gap-4">
        <h2
          id="alternates-lane-heading"
          className="font-mono text-xs uppercase tracking-widest text-ink-muted"
        >
          Alternates lane
        </h2>
        <span className="font-mono text-[11px] uppercase tracking-wider text-ink-muted">
          {shots.length} shot{shots.length === 1 ? "" : "s"} · drafts say so
        </span>
      </div>
      {shots.length === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">
          No generated clips yet. Agent renders appear here as alternates the
          moment the API reports them — nothing on this screen is simulated.
        </p>
      ) : (
        <ul className="mt-3 space-y-3">
          {shots.map((shot) => (
            <ShotCard key={shot.shot_id} shot={shot} fetchMediaUrl={resolveMedia} />
          ))}
        </ul>
      )}
    </section>
  );
}
