/** ⌘K command list — no extra fuzzy library (Step 5). */

import { ROUTES } from "@/lib/navigation";
import type { Job } from "@/types/api";

export type PaletteKind = "route" | "job" | "lens";

export interface PaletteCommand {
  id: string;
  label: string;
  hint: string;
  kind: PaletteKind;
}

export const LENS_COMMAND: PaletteCommand = {
  id: "lens",
  label: "Toggle Lens",
  hint: "Reveal collapsed lanes and the filter row",
  kind: "lens",
};

export function routeCommands(): PaletteCommand[] {
  return ROUTES.map((entry) => ({
    id: `route:${entry.id}`,
    label: entry.label,
    hint: entry.path === "/" ? "Season board" : entry.path,
    kind: "route",
  }));
}

export function jobCommands(jobs: readonly Job[]): PaletteCommand[] {
  return jobs.map((job) => ({
    id: `job:${job.job_id}`,
    label: job.job_id,
    hint: job.station,
    kind: "job",
  }));
}

/** Observed jobs only — never invents ids that were not on the wire. */
export function allCommands(jobs: readonly Job[]): PaletteCommand[] {
  return [...routeCommands(), ...jobCommands(jobs), LENS_COMMAND];
}

export function pathForRouteCommand(commandId: string): string {
  const routeId = commandId.startsWith("route:") ? commandId.slice("route:".length) : commandId;
  return ROUTES.find((entry) => entry.id === routeId)?.path ?? "/";
}

export function fuzzyScore(query: string, text: string): number {
  const needle = query.trim().toLowerCase();
  if (!needle) return 1;
  const hay = text.toLowerCase();
  if (hay.includes(needle)) return 2;
  let offset = 0;
  for (const character of hay) {
    if (character === needle[offset]) offset += 1;
    if (offset === needle.length) return 1;
  }
  return 0;
}

export function filterCommands(
  commands: readonly PaletteCommand[],
  query: string,
): PaletteCommand[] {
  return commands
    .map((command) => ({
      command,
      score: Math.max(
        fuzzyScore(query, command.label),
        fuzzyScore(query, command.id),
        fuzzyScore(query, command.hint),
      ),
    }))
    .filter(({ score }) => score > 0)
    .sort(
      (left, right) =>
        right.score - left.score || left.command.label.localeCompare(right.command.label),
    )
    .map(({ command }) => command);
}
