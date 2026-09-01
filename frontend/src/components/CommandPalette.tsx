import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { fadeRise } from "@/lib/motion";
import { filterCommands, type PaletteCommand } from "@/lib/palette";

interface CommandPaletteProps {
  open: boolean;
  commands: readonly PaletteCommand[];
  returnFocusRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onSelect: (command: PaletteCommand) => void;
}

export default function CommandPalette({
  open,
  commands,
  returnFocusRef,
  onClose,
  onSelect,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const matches = filterCommands(commands, query);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((current) =>
          matches.length === 0 ? 0 : Math.min(matches.length - 1, current + 1),
        );
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((current) => Math.max(0, current - 1));
      }
      if (event.key === "Enter") {
        const command = matches[active];
        if (command) {
          event.preventDefault();
          onSelect(command);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, matches, active, onClose, onSelect]);

  const activeId = matches[active] ? `${listId}-${matches[active].id}` : undefined;

  return (
    <AnimatePresence
      onExitComplete={() => {
        if (!open) returnFocusRef.current?.focus();
      }}
    >
      {open ? (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Command palette"
          className="fixed inset-0 z-[80] grid place-items-start justify-center pt-[15vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
        >
          <button
            type="button"
            aria-label="Dismiss command palette"
            className="absolute inset-0"
            style={{ backgroundColor: "var(--scrim)" }}
            onClick={onClose}
          />
          <motion.div
            variants={fadeRise}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="relative z-10 w-[min(40rem,calc(100%-2rem))] rounded-md border border-line bg-surface-2 shadow-[var(--shadow-lift)]"
          >
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Jump to a route, job, or Lens"
              aria-autocomplete="list"
              aria-controls={listId}
              aria-activedescendant={activeId}
              className="w-full rounded-t-md border-b border-line bg-surface-2 px-4 py-3 text-sm text-ink placeholder:text-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten"
            />
            <ul id={listId} role="listbox" className="max-h-80 overflow-y-auto p-2">
              {matches.length === 0 ? (
                <li className="px-3 py-2 font-mono text-xs uppercase tracking-widest text-ink-muted">
                  No matching commands
                </li>
              ) : (
                matches.map((command, index) => {
                  const selected = index === active;
                  return (
                    <li key={command.id} role="presentation">
                      <button
                        type="button"
                        id={`${listId}-${command.id}`}
                        role="option"
                        aria-selected={selected}
                        onMouseEnter={() => setActive(index)}
                        onClick={() => onSelect(command)}
                        className={`flex w-full items-baseline justify-between gap-4 rounded-sm px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten ${
                          selected ? "bg-surface-1 text-ink" : "text-ink-muted"
                        }`}
                      >
                        <span className="text-sm text-ink">{command.label}</span>
                        <span className="font-mono text-xs uppercase tracking-wider">
                          {command.hint}
                        </span>
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
