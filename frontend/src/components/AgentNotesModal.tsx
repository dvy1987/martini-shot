import { useEffect } from "react";

import { composeAgentNotes, type AgentNotes } from "../lib/agentNotes";

export function AgentNotesModal({
  title,
  notes,
  onClose,
}: {
  title: string;
  notes: AgentNotes;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const paragraphs = composeAgentNotes(notes)
    .split(/\n\n+/)
    .map((part) => part.trim())
    .filter(Boolean);

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-bg/80 px-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-notes-title"
        className="w-full max-w-xl rounded-md border border-line bg-surface-1 p-5"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-ink-muted">
              Agent notes
            </p>
            <h2 id="agent-notes-title" className="mt-1 text-lg text-ink">
              {title}
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
        <div className="mt-4 space-y-3">
          {paragraphs.map((paragraph) => (
            <p key={paragraph} className="text-sm leading-relaxed text-ink">
              {paragraph}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
