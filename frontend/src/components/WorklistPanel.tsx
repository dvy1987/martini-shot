/** Ranked finishing work. Passed ticks green. Waiting rows can be reordered. */
import { cost } from "@/lib/formatters";
import type { Worklist, WorklistItem } from "@/types/api";

interface WorklistPanelProps {
  worklist: Worklist | null;
  onReorder?: (order: string[]) => void;
}

export function nextWorklistOrder(
  items: WorklistItem[],
  id: string,
  direction: -1 | 1,
): string[] {
  const waitingAt = items
    .map((item, index) => (item.status === "waiting" ? index : -1))
    .filter((index) => index >= 0);
  const pos = waitingAt.findIndex((index) => items[index]?.id === id);
  const swapWith = pos + direction;
  if (pos < 0 || swapWith < 0 || swapWith >= waitingAt.length) {
    return items.map((item) => item.id);
  }
  const next = [...items];
  const a = waitingAt[pos];
  const b = waitingAt[swapWith];
  const left = next[a];
  const right = next[b];
  if (!left || !right) {
    return items.map((item) => item.id);
  }
  next[a] = right;
  next[b] = left;
  return next.map((item) => item.id);
}

function itemTone(status: string): string {
  if (status === "passed") return "text-signal";
  if (status === "failed" || status === "needs_human") return "text-danger";
  if (status === "queued" || status === "running") return "text-agent";
  return "text-ink-muted";
}

function itemGlyph(status: string): string {
  if (status === "passed") return "◼";
  if (status === "failed" || status === "needs_human") return "⚑";
  if (status === "queued") return "●";
  if (status === "running") return "▶";
  if (status === "paused" || status === "waiting") return "⏸";
  return "·";
}

export default function WorklistPanel({ worklist, onReorder }: WorklistPanelProps) {
  if (!worklist) {
    return null;
  }
  const waitingIds = worklist.items
    .filter((item) => item.status === "waiting")
    .map((item) => item.id);
  return (
    <section className="mt-6 rounded-md border border-line bg-surface-1">
      <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink-muted">
          Finishing worklist
        </h2>
        <p className="font-mono text-xs text-ink-muted">
          {worklist.status} · budget {cost(worklist.budget_micros)} · spent{" "}
          {cost(worklist.spent_micros)}
        </p>
        {worklist.rank_reason ? (
          <p className="basis-full text-sm text-ink">{worklist.rank_reason}</p>
        ) : null}
      </header>
      {worklist.items.length > 0 ? (
        <table className="w-full border-collapse text-left">
          <thead className="bg-surface-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
            <tr>
              <th className="border-b border-line px-4 py-2 font-normal">Rank</th>
              <th className="border-b border-line px-4 py-2 font-normal">Station</th>
              <th className="border-b border-line px-4 py-2 font-normal">Why</th>
              <th className="border-b border-line px-4 py-2 font-normal">Impact</th>
              <th className="border-b border-line px-4 py-2 font-normal">Status</th>
              <th className="border-b border-line px-4 py-2 font-normal">Order</th>
            </tr>
          </thead>
          <tbody>
            {worklist.items.map((item, index) => {
              const waitingPos = waitingIds.indexOf(item.id);
              const canUp = item.status === "waiting" && waitingPos > 0;
              const canDown =
                item.status === "waiting" && waitingPos >= 0 && waitingPos < waitingIds.length - 1;
              return (
                <tr key={item.id}>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink-muted">
                    {index + 1}
                  </td>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink">
                    {item.station.replaceAll("_", " ")}
                  </td>
                  <td className="border-b border-line px-4 py-2 text-sm text-ink">
                    {item.summary ?? ""}
                    {item.blocked_by && item.blocked_by.length > 0 ? (
                      <span className="mt-1 block font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                        waits on {item.blocked_by.map((id) => id.split("::")[0]).join(", ")}
                      </span>
                    ) : null}
                  </td>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink-muted">
                    {item.impact ?? ""}
                    {item.kind && item.kind !== "none" ? ` · ${item.kind}` : ""}
                  </td>
                  <td
                    className={`border-b border-line px-4 py-2 font-mono text-xs ${itemTone(item.status)}`}
                  >
                    <span aria-hidden className="mr-2">
                      {itemGlyph(item.status)}
                    </span>
                    {item.status === "passed" ? "locked" : item.status.replaceAll("_", " ")}
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    {item.status === "waiting" && onReorder ? (
                      <div className="flex gap-1">
                        <button
                          type="button"
                          disabled={!canUp}
                          aria-label={`Move ${item.station} up`}
                          onClick={() =>
                            onReorder(nextWorklistOrder(worklist.items, item.id, -1))
                          }
                          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-ink disabled:opacity-40"
                        >
                          Up
                        </button>
                        <button
                          type="button"
                          disabled={!canDown}
                          aria-label={`Move ${item.station} down`}
                          onClick={() =>
                            onReorder(nextWorklistOrder(worklist.items, item.id, 1))
                          }
                          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-ink disabled:opacity-40"
                        >
                          Down
                        </button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="px-4 py-3 font-mono text-xs text-ink-muted">
          {worklist.status === "inspecting"
            ? "Stations are looking at the clips."
            : "No ranked work yet."}
        </p>
      )}
      {worklist.attendance.length > 0 ? (
        <table className="w-full border-collapse border-t border-line text-left">
          <thead className="bg-surface-2 font-mono text-xs uppercase tracking-wider text-ink-muted">
            <tr>
              <th className="border-b border-line px-4 py-2 font-normal">Station look</th>
              <th className="border-b border-line px-4 py-2 font-normal">Note</th>
              <th className="border-b border-line px-4 py-2 font-normal">Impact</th>
            </tr>
          </thead>
          <tbody>
            {worklist.attendance.map((row, index) => (
              <tr key={`${row.station}-${row.shot_id ?? ""}-${index}`}>
                <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink-muted">
                  {row.station.replaceAll("_", " ")}
                </td>
                <td className="border-b border-line px-4 py-2 text-sm text-ink">
                  {row.status === "empty" ? "" : row.summary}
                </td>
                <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink-muted">
                  {row.status === "empty" ? "" : row.impact}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}
