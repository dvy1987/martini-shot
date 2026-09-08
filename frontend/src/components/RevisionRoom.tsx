import { useEffect, useState } from "react";

import {
  createScriptVersion,
  listScripts,
  proposeRegenerateSpans,
  type ScriptVersion,
} from "@/api/endpoints";

interface RevisionRoomProps {
  projectId: string;
  list?: typeof listScripts;
  create?: typeof createScriptVersion;
  regenerate?: typeof proposeRegenerateSpans;
}

export default function RevisionRoom({
  projectId,
  list = listScripts,
  create = createScriptVersion,
  regenerate = proposeRegenerateSpans,
}: RevisionRoomProps) {
  const [versions, setVersions] = useState<ScriptVersion[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [last, setLast] = useState<ScriptVersion | null>(null);
  const [proposedId, setProposedId] = useState<string | null>(null);
  const head = versions[versions.length - 1] ?? last;

  useEffect(() => {
    let cancelled = false;
    void list(projectId)
      .then((rows) => {
        if (cancelled) return;
        setVersions(rows);
        const latest = rows[rows.length - 1];
        if (latest) setText(latest.text);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Scripts unavailable.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, list]);

  async function save() {
    setPending(true);
    setError(null);
    try {
      const version = await create(projectId, {
        text,
        based_on_version_id: head?.version_id ?? null,
        consult_agent: true,
      });
      setLast(version);
      setVersions((rows) => [...rows.filter((row) => row.version_id !== version.version_id), version]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Script save failed.");
    } finally {
      setPending(false);
    }
  }

  async function regenerateAffected() {
    if (!last?.version_id || !last.affected?.length) return;
    setPending(true);
    setError(null);
    try {
      const result = await regenerate(projectId, last.version_id, {
        spans: last.affected,
        reason: "Update the script: regenerate affected spans",
      });
      setProposedId(result.approval_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Regenerate proposal failed.");
    } finally {
      setPending(false);
    }
  }

  const affectedShots = [
    ...new Set((last?.affected ?? []).flatMap((row) => row.affected_shot_ids)),
  ];

  return (
    <section
      aria-labelledby="revision-room-heading"
      className="mt-8 rounded-md border border-line bg-surface-1 p-4"
    >
      <h2
        id="revision-room-heading"
        className="font-mono text-xs uppercase tracking-widest text-ink-muted"
      >
        Update the script
      </h2>
      <p className="mt-2 text-sm text-ink-muted">
        Edit the script below. Martini Shot will identify the affected clips and suggest updated versions for your review.
      </p>
      <label className="mt-3 grid gap-1 text-xs text-ink-muted">
        Script text
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={5}
          className="rounded-sm border border-line bg-surface-2 px-2 py-1 font-mono text-sm text-ink"
        />
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending || !text.trim()}
          onClick={() => void save()}
          className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
        >
          {pending ? "Saving…" : "Save script"}
        </button>
        {affectedShots.length > 0 ? (
          <button
            type="button"
            disabled={pending}
            onClick={() => void regenerateAffected()}
            className="rounded-sm border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tungsten disabled:text-ink-muted"
          >
            Suggest updated clips
          </button>
        ) : null}
      </div>
      {last?.agent ? (
        <p className="mt-2 text-sm text-ink-muted">{last.agent.rationale}</p>
      ) : null}
      {affectedShots.length > 0 ? (
        <p className="mt-2 font-mono text-[11px] text-tungsten">
          Affected clips: {affectedShots.join(", ")}
        </p>
      ) : null}
      {proposedId ? (
        <p className="mt-2 font-mono text-[11px] text-tungsten">Suggestion created: {proposedId}</p>
      ) : null}
      {error ? (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
