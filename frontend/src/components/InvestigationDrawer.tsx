import { useEffect, useRef, useState, type RefObject } from "react";
import { AnimatePresence, motion } from "framer-motion";

import AgentPanel from "@/components/AgentPanel";
import { cost } from "@/lib/formatters";
import { chromeTween, drawerVariants } from "@/lib/motion";
import { statusMetaOrUnknown } from "@/lib/status";
import type { Deliberation, Job } from "@/types/api";

export interface InvestigationDrawerError {
  code: string;
  message: string;
}

interface InvestigationDrawerProps {
  open: boolean;
  job: Job | null;
  isLoading: boolean;
  error: InvestigationDrawerError | null;
  deliberation?: Deliberation | null;
  returnFocusRef: RefObject<HTMLElement | null>;
  onRetry?: () => void;
  onClose: () => void;
}

function SectionLabel({ children }: { children: string }) {
  return (
    <h3 className="font-mono text-xs uppercase tracking-widest text-ink-muted">
      {children}
    </h3>
  );
}

function DrawerBody({
  job,
  isLoading,
  error,
  deliberation,
  onRetry,
}: Pick<
  InvestigationDrawerProps,
  "job" | "isLoading" | "error" | "deliberation" | "onRetry"
>) {
  const [showEvidence, setShowEvidence] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);

  useEffect(() => {
    setShowEvidence(false);
    setShowTranscript(false);
  }, [job?.job_id]);

  if (isLoading) {
    return (
      <div aria-label="Loading investigation" aria-busy="true" className="space-y-4">
        <div className="h-16 rounded-md bg-surface-2" />
        <div className="grid grid-cols-2 gap-2">
          <div className="h-14 rounded-md bg-surface-2" />
          <div className="h-14 rounded-md bg-surface-2" />
        </div>
        <div className="h-24 rounded-md bg-surface-2" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-line bg-surface-2 p-4">
        <p className="text-lg text-ink">Case file unavailable.</p>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">{error.message}</p>
        <p className="mt-3 font-mono text-xs uppercase tracking-wider text-ink-muted">
          {error.code}
        </p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 rounded-sm border border-line bg-surface-1 px-3 py-2 font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
          >
            Retry case file
          </button>
        ) : null}
      </div>
    );
  }

  if (!job) {
    return (
      <div className="rounded-md border border-line bg-surface-2 p-4">
        <p className="text-lg text-ink">No job record returned.</p>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          The API did not return an observable case file for this selection.
        </p>
      </div>
    );
  }

  const status = statusMetaOrUnknown(job.status);
  const inputRefCount = job.input_refs.length;

  return (
    <div className="space-y-6">
      <section aria-labelledby="case-file-status">
        <SectionLabel>Current state</SectionLabel>
        <div className="mt-2 rounded-md border border-line bg-surface-2 p-4">
          <div className={`flex items-center gap-3 font-mono text-sm ${status.textClass}`}>
            <span aria-hidden className="text-lg">
              {status.glyph}
            </span>
            <span id="case-file-status">{status.term}</span>
          </div>
          <p className="mt-2 text-sm text-ink-muted">{status.hint}</p>
        </div>
      </section>

      <section aria-label="Job accounting" className="grid grid-cols-2 gap-2">
        <div className="rounded-md border border-line bg-surface-2 p-3">
          <SectionLabel>Attempts</SectionLabel>
          <p className="mt-2 font-mono text-lg text-ink">{job.attempts}</p>
        </div>
        <div className="rounded-md border border-line bg-surface-2 p-3">
          <SectionLabel>Cost</SectionLabel>
          <p className="mt-2 font-mono text-lg text-ink">
            {job.cost_micros !== undefined ? cost(job.cost_micros) : "—"}
          </p>
        </div>
      </section>

      <section aria-labelledby="case-file-error">
        <SectionLabel>Error report</SectionLabel>
        <div className="mt-2 rounded-md border border-line bg-surface-2 p-4">
          {job.error ? (
            <>
              <p id="case-file-error" className="font-mono text-xs text-danger">
                {job.error.code}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-ink">{job.error.message}</p>
            </>
          ) : (
            <p id="case-file-error" className="text-sm text-ink-muted">No error reported.</p>
          )}
        </div>
      </section>

      <section aria-labelledby="case-file-inputs">
        <div className="flex items-baseline justify-between gap-4">
          <SectionLabel>Input refs</SectionLabel>
          <span className="font-mono text-xs text-ink-muted">
            {inputRefCount > 0 ? `${inputRefCount} reported` : "none reported"}
          </span>
        </div>
        <div className="mt-2 rounded-md border border-line bg-surface-2 p-4">
          <p id="case-file-inputs" className="text-sm text-ink-muted">
            These are the source references reported by the job API.
          </p>
        </div>
      </section>

      {deliberation ? <AgentPanel deliberation={deliberation} /> : null}

      <section className="border-t border-line pt-5">
        <button
          type="button"
          aria-expanded={showEvidence}
          aria-controls="case-file-evidence"
          onClick={() => setShowEvidence((visible) => !visible)}
          className="flex w-full items-center justify-between gap-4 text-left font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:text-tungsten focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
        >
          <span>{showEvidence ? "Hide evidence" : "Show evidence"}</span>
          <span aria-hidden>{showEvidence ? "−" : "+"}</span>
        </button>
        {showEvidence ? (
          <div id="case-file-evidence" className="mt-3 space-y-2">
            <p className="text-sm text-ink-muted">API-reported input references</p>
            {job.input_refs.length > 0 ? (
              job.input_refs.map((inputRef) => (
                <span
                  key={inputRef}
                  className="block break-all rounded-sm border border-line bg-surface-2 px-3 py-2 font-mono text-xs text-ink"
                >
                  {inputRef}
                </span>
              ))
            ) : (
              <p className="text-sm text-ink-muted">No input references reported.</p>
            )}
          </div>
        ) : null}
      </section>

      <section className="border-t border-line pt-5">
        <button
          type="button"
          aria-expanded={showTranscript}
          aria-controls="case-file-transcript"
          onClick={() => setShowTranscript((visible) => !visible)}
          className="flex w-full items-center justify-between gap-4 text-left font-mono text-xs uppercase tracking-wider text-ink transition-colors ease-chrome hover:text-tungsten focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
        >
          <span>{showTranscript ? "Hide transcript" : "Show transcript"}</span>
          <span aria-hidden>{showTranscript ? "−" : "+"}</span>
        </button>
        {showTranscript ? (
          <div id="case-file-transcript" className="mt-3">
            <p className="mb-2 text-sm text-ink-muted">Raw API job record</p>
            <pre className="max-h-72 overflow-auto rounded-md border border-line bg-surface-2 p-3 font-mono text-xs leading-relaxed text-ink">
              {JSON.stringify(job, null, 2)}
            </pre>
          </div>
        ) : null}
      </section>
    </div>
  );
}

export default function InvestigationDrawer({
  open,
  job,
  isLoading,
  error,
  deliberation = null,
  returnFocusRef,
  onRetry,
  onClose,
}: InvestigationDrawerProps) {
  const drawerRef = useRef<HTMLElement | null>(null);
  const focusBoundaryActiveRef = useRef(false);
  const openRef = useRef(open);

  useEffect(() => {
    openRef.current = open;
    if (open) {
      focusBoundaryActiveRef.current = true;
      drawerRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!focusBoundaryActiveRef.current) return;
      if (event.key === "Escape") {
        if (openRef.current) onClose();
        return;
      }
      if (event.key !== "Tab" || !drawerRef.current) return;

      const focusable = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) {
        event.preventDefault();
        drawerRef.current.focus();
        return;
      }

      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === drawerRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  return (
    <AnimatePresence
      onExitComplete={() => {
        if (!open) {
          focusBoundaryActiveRef.current = false;
          returnFocusRef.current?.focus();
        }
      }}
    >
      {open ? (
        <motion.div
          key="investigation-layer"
          initial="hidden"
          animate="visible"
          exit="exit"
          variants={{
            hidden: {},
            visible: { transition: { when: "beforeChildren" } },
            exit: { transition: { when: "afterChildren" } },
          }}
          className="pointer-events-none fixed inset-0 z-40"
        >
          <motion.button
            type="button"
            aria-label="Close investigation backdrop"
            onClick={onClose}
            variants={{
              hidden: { opacity: 0 },
              visible: { opacity: 1, transition: chromeTween },
              exit: { opacity: 0, transition: chromeTween },
            }}
            className="pointer-events-auto absolute inset-0 cursor-default bg-bg/70 focus-visible:outline-none"
          />
          <motion.aside
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="investigation-drawer-label investigation-drawer-title"
            tabIndex={-1}
            variants={drawerVariants}
            className="pointer-events-auto absolute right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-line bg-surface-1 shadow-2xl focus-visible:outline-none"
          >
            <header className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-6 py-5">
              <div>
                <p
                  id="investigation-drawer-label"
                  className="font-mono text-xs uppercase tracking-widest text-ink-muted"
                >
                  Investigation card
                </p>
                <h2 id="investigation-drawer-title" className="mt-1 text-xl text-ink">
                  {job?.job_id ?? "Loading case file"}
                </h2>
              </div>
              <button
                type="button"
                aria-label="Close investigation drawer"
                onClick={onClose}
                className="rounded-sm border border-line px-2 py-1 font-mono text-xs text-ink-muted transition-colors ease-chrome hover:border-ink-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
              >
                Close
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
              <DrawerBody
                job={job}
                isLoading={isLoading}
                error={error}
                deliberation={deliberation}
                onRetry={onRetry}
              />
            </div>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}