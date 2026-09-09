/** This-run briefing: health, spend, time left, automatic actions — in the product. */
import { useEffect, useState, type ReactNode } from "react";

import { buildRunBriefing, type AttentionItem, type BriefingSection } from "@/lib/runBriefing";
import { stationName } from "@/lib/stations";
import { statusMetaOrUnknown } from "@/lib/status";
import type { Job, RunPulse, Worklist } from "@/types/api";

interface RunPulseProps {
  pulse: RunPulse | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  liveJobs?: readonly Job[];
  worklist?: Worklist | null;
  onJumpToJob?: (jobId: string) => void;
}

function headingToneClass(tone: BriefingSection["tone"]): string {
  if (tone === "ok") return "text-signal";
  if (tone === "fail") return "text-danger";
  return "text-ink-muted";
}

export default function RunPulseStrip({
  pulse,
  isLoading = false,
  errorMessage = null,
  liveJobs,
  worklist,
  onJumpToJob,
}: RunPulseProps) {
  const [openId, setOpenId] = useState<BriefingSection["id"] | null>(null);

  if (isLoading && !pulse) {
    return (
      <section
        aria-busy="true"
        aria-label="Loading this run"
        className="space-y-6"
      >
        <div className="h-3 w-64 rounded-sm bg-surface-2" />
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
          <div className="min-h-52 rounded-md border border-line bg-surface-1" />
        </div>
      </section>
    );
  }

  if (errorMessage && !pulse) {
    return (
      <section className="rounded-md border border-line bg-surface-1 px-5 py-6">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">This run</h2>
        <p className="mt-3 text-sm leading-relaxed text-ink-muted">{errorMessage}</p>
      </section>
    );
  }

  if (!pulse) {
    return null;
  }

  const briefing = buildRunBriefing(pulse, liveJobs, worklist);
  const openSection = briefing.sections.find((section) => section.id === openId) ?? null;

  return (
    <section aria-labelledby="run-pulse-heading" className="space-y-8">
      <header>
        <h2 id="run-pulse-heading" className="sr-only">
          {briefing.title}
        </h2>
        <p className="max-w-2xl text-sm leading-relaxed text-ink-muted">{briefing.sourceLine}</p>
      </header>
      <div className="grid gap-6 sm:grid-cols-2">
        {briefing.sections.map((section) => (
          <article
            key={section.id}
            aria-labelledby={`pulse-${section.id}`}
            className="flex min-h-52 flex-col rounded-md border border-line bg-surface-1 px-5 py-6"
          >
            <h3 id={`pulse-${section.id}`}>
              <button
                type="button"
                onClick={() => setOpenId(section.id)}
                className={`font-mono text-[10px] uppercase tracking-wider underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten ${headingToneClass(section.tone)}`}
              >
                {section.title}
              </button>
            </h3>
            <p className="mt-4 text-lg leading-snug text-ink">{section.meaning}</p>
            <p className="mt-4 flex-1 text-sm leading-relaxed text-ink">{section.detail}</p>
          </article>
        ))}
      </div>
      {openSection ? (
        <PulseFactModal
          title={openSection.id === "health" && briefing.attention.length > 0 ? "What needs you" : openSection.title}
          onClose={() => setOpenId(null)}
        >
          {openSection.id === "health" ? (
            <HealthModalBody
              section={openSection}
              attention={briefing.attention}
              onJumpToJob={(jobId) => {
                setOpenId(null);
                onJumpToJob?.(jobId);
              }}
            />
          ) : null}
          {openSection.id === "spend" ? (
            <p className="text-sm leading-relaxed text-ink">{openSection.detail}</p>
          ) : null}
          {openSection.id === "time" ? (
            <p className="text-sm leading-relaxed text-ink">{openSection.detail}</p>
          ) : null}
          {openSection.id === "actions" ? (
            <ActionsModalBody
              actions={briefing.actions}
              empty={openSection.detail}
              onJumpToJob={(jobId) => {
                setOpenId(null);
                onJumpToJob?.(jobId);
              }}
            />
          ) : null}
        </PulseFactModal>
      ) : null}
      <div className="rounded-md border border-line bg-surface-1 px-5 py-6">
        <h3 className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Jobs this run</h3>
        {(pulse.jobs ?? []).length === 0 ? (
          <p className="mt-4 text-sm leading-relaxed text-ink-muted">No jobs on this project yet.</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {(pulse.jobs ?? []).map((row) => {
              const meta = statusMetaOrUnknown(row.status);
              const stage = stationName(row.station);
              return (
                <li key={row.job_id}>
                  {onJumpToJob ? (
                    <button
                      type="button"
                      aria-label={`${stage} · ${row.clip}`}
                      onClick={() => onJumpToJob(row.job_id)}
                      className="flex w-full items-baseline justify-between gap-4 text-left text-sm text-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
                    >
                      <span className="min-w-0 truncate">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                          {stage}
                        </span>{" "}
                        {row.clip}
                      </span>
                      <span className={`shrink-0 font-mono text-[10px] uppercase ${meta.textClass}`}>
                        {meta.term}
                      </span>
                    </button>
                  ) : (
                    <p className="flex items-baseline justify-between gap-4 text-sm text-ink">
                      <span className="min-w-0 truncate">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                          {stage}
                        </span>{" "}
                        {row.clip}
                      </span>
                      <span className={`shrink-0 font-mono text-[10px] uppercase ${meta.textClass}`}>
                        {meta.term}
                      </span>
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

function PulseFactModal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-bg/80 px-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pulse-fact-title"
        className="max-h-[80vh] w-full max-w-xl overflow-y-auto rounded-md border border-line bg-surface-1 p-5"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="pulse-fact-title" className="text-lg text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-line px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted transition-colors ease-chrome hover:border-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Close
          </button>
        </div>
        <div className="mt-4 space-y-4">{children}</div>
      </div>
    </div>
  );
}

function HealthModalBody({
  section,
  attention,
  onJumpToJob,
}: {
  section: BriefingSection;
  attention: AttentionItem[];
  onJumpToJob?: (jobId: string) => void;
}) {
  if (attention.length === 0) {
    return <p className="text-sm leading-relaxed text-ink">{section.detail}</p>;
  }
  return (
    <ul className="space-y-6">
      {attention.map((item) => (
        <li key={item.jobId} className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-wider text-agent">{item.heading}</p>
          <p className="text-sm text-ink-muted">{item.clip}</p>
          <p className="text-lg leading-snug text-tungsten">{item.why}</p>
          <p className="text-sm leading-relaxed text-ink">{item.next}</p>
          {onJumpToJob ? (
            <button
              type="button"
              aria-label={`Open ${item.lane} · ${item.clip}`}
              onClick={() => onJumpToJob(item.jobId)}
              className="font-mono text-[10px] uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              Open on Timeline
            </button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ActionsModalBody({
  actions,
  empty,
  onJumpToJob,
}: {
  actions: { kind: string; label: string; text: string; jobId?: string | null }[];
  empty: string;
  onJumpToJob?: (jobId: string) => void;
}) {
  if (actions.length === 0) {
    return <p className="text-sm leading-relaxed text-ink">{empty}</p>;
  }
  return (
    <ul className="space-y-4">
      {actions.map((item, index) => (
        <li key={`${item.kind}-${item.jobId ?? index}`} className="text-sm leading-relaxed text-ink">
          <p>
            <span className="font-mono text-[10px] uppercase tracking-wider text-agent">{item.label}</span>{" "}
            {item.text}
          </p>
          {item.jobId && onJumpToJob ? (
            <button
              type="button"
              onClick={() => onJumpToJob(item.jobId ?? "")}
              className="mt-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            >
              Open on Timeline
            </button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
