import { useQuery } from "@tanstack/react-query";

import { getProject, getWorklist, listProjectShots } from "@/api/endpoints";
import AlternatesLane from "@/components/AlternatesLane";
import DirectedEditStudio from "@/components/DirectedEditStudio";
import EmptyState from "@/components/EmptyState";
import RevisionRoom from "@/components/RevisionRoom";
import { isNotFound } from "@/lib/errors";
import type { BackendReach } from "@/types/api";

interface ChangesRouteProps {
  backend: BackendReach;
  selectedProjectId: string | null;
}

export default function ChangesRoute({
  backend,
  selectedProjectId,
}: ChangesRouteProps) {
  const shotsQuery = useQuery({
    queryKey: ["shots", selectedProjectId],
    queryFn: () => listProjectShots(selectedProjectId ?? ""),
    enabled: backend === "up" && selectedProjectId !== null,
    retry: false,
  });
  // Same query keys App.tsx uses for its SSE-fed caches (job.updated /
  // worklist.updated), so this screen sees live job status with no polling.
  const projectQuery = useQuery({
    queryKey: ["project", selectedProjectId],
    queryFn: () => getProject(selectedProjectId ?? ""),
    enabled: backend === "up" && selectedProjectId !== null,
  });
  const worklistQuery = useQuery({
    queryKey: ["worklist", selectedProjectId],
    queryFn: async () => {
      try {
        return await getWorklist(selectedProjectId ?? "");
      } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
      }
    },
    enabled: backend === "up" && selectedProjectId !== null,
    retry: false,
  });

  if (backend === "checking") {
    return (
      <p className="px-6 py-10 font-mono text-xs uppercase tracking-widest text-ink-muted" aria-live="polite">
        Checking changes…
      </p>
    );
  }

  if (backend === "down") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Changes</h1>
        <EmptyState
          glyph="✎"
          title="Changes are unavailable"
          body="The service is unavailable, so shot edits and script updates cannot be loaded."
        />
      </section>
    );
  }

  if (!selectedProjectId) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="sr-only">Changes</h1>
        <EmptyState
          glyph="✎"
          title="No project selected"
          body="Select a project on the timeline first. Bespoke changes are shown for one project at a time."
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-4 px-6 py-8" aria-labelledby="changes-heading">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-muted">Studio</p>
        <h1 id="changes-heading" className="mt-1 text-2xl text-ink">
          Bespoke changes
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted">
          Ask for a longer take, a picture fix, a lighting look, extra coverage, or a camera move.
          New versions stay attached to the shot until you make one current. Script edits live here too.
        </p>
      </header>

      {shotsQuery.isError ? (
        <p className="border-l-2 border-danger pl-3 text-sm text-danger">
          Shot versions could not be loaded. Check the connection and try again.
        </p>
      ) : null}

      <DirectedEditStudio
        projectId={selectedProjectId}
        shots={shotsQuery.data ?? []}
        jobs={projectQuery.data?.jobs ?? []}
        worklist={worklistQuery.data ?? null}
      />
      <AlternatesLane shots={shotsQuery.data ?? []} />
      <RevisionRoom projectId={selectedProjectId} />
    </section>
  );
}
