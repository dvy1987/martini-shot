import { Route, Routes } from "react-router-dom";

import TopBar from "@/components/TopBar";
import { useBackendHealth } from "@/hooks/useBackendHealth";
import { useSSE } from "@/hooks/useSSE";
import ApprovalsRoute from "@/pages/ApprovalsRoute";
import ReportsRoute from "@/pages/ReportsRoute";
import TimelineRoute from "@/pages/TimelineRoute";

/**
 * App shell. Until the backend exists (gate G1) the health probe fails and the
 * SSE stream is null — every view truthfully renders its designed empty state
 * (frontend/AGENTS.md: no-backend period is expected; mock APIs are banned).
 */
export default function App() {
  const health = useBackendHealth();
  // The real stream needs a selected project id; wiring lands with the backend.
  const sse = useSSE(null);

  return (
    <div className="flex h-dvh flex-col bg-bg text-ink">
      <TopBar connected={health.isSuccess} sseStatus={sse.status} />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<TimelineRoute />} />
          <Route path="/approvals" element={<ApprovalsRoute />} />
          <Route path="/reports" element={<ReportsRoute />} />
          <Route path="*" element={<TimelineRoute />} />
        </Routes>
      </main>
    </div>
  );
}
