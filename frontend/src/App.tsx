import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Route, Routes } from "react-router-dom";

import { projectEventsUrl } from "@/api/endpoints";
import TopBar from "@/components/TopBar";
import { useBackendHealth } from "@/hooks/useBackendHealth";
import { useSSE } from "@/hooks/useSSE";
import { jobFromSseEvent, upsertJob } from "@/lib/timeline";
import ApprovalsRoute from "@/pages/ApprovalsRoute";
import ReportsRoute from "@/pages/ReportsRoute";
import TimelineRoute from "@/pages/TimelineRoute";
import type { Project, SseEvent } from "@/types/api";

/**
 * App shell. Until the backend exists (gate G1) the health probe fails and the
 * SSE stream is null — every view truthfully renders its designed empty state
 * (frontend/AGENTS.md: no-backend period is expected; mock APIs are banned).
 */
export default function App() {
  const health = useBackendHealth();
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const handleSseEvent = useCallback(
    (event: SseEvent) => {
      const job = jobFromSseEvent(event);
      if (!job || !selectedProjectId || job.project_id !== selectedProjectId) return;

      queryClient.setQueryData<Project>(["project", selectedProjectId], (project) => {
        if (!project) return project;
        return { ...project, jobs: upsertJob(project.jobs ?? [], job) };
      });
    },
    [queryClient, selectedProjectId],
  );

  const sse = useSSE(
    selectedProjectId ? projectEventsUrl(selectedProjectId) : null,
    handleSseEvent,
  );

  return (
    <div className="flex h-dvh flex-col bg-bg text-ink">
      <TopBar connected={health.isSuccess} sseStatus={sse.status} />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <Routes>
          <Route
            path="/"
            element={
              <TimelineRoute
                selectedProjectId={selectedProjectId}
                onSelectedProjectIdChange={setSelectedProjectId}
              />
            }
          />
          <Route path="/approvals" element={<ApprovalsRoute />} />
          <Route path="/reports" element={<ReportsRoute />} />
          <Route
            path="*"
            element={
              <TimelineRoute
                selectedProjectId={selectedProjectId}
                onSelectedProjectIdChange={setSelectedProjectId}
              />
            }
          />
        </Routes>
      </main>
    </div>
  );
}
