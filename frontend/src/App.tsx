import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { getProject, listApprovals, listProjects, projectEventsUrl } from "@/api/endpoints";
import CommandPalette from "@/components/CommandPalette";
import SlateDeck from "@/components/SlateDeck";
import TopBar from "@/components/TopBar";
import { useBackendHealth } from "@/hooks/useBackendHealth";
import { useSSE } from "@/hooks/useSSE";
import { allCommands, pathForRouteCommand, type PaletteCommand } from "@/lib/palette";
import { slateForRoute } from "@/lib/slates";
import { deliberationFromSseEvent, upsertDeliberation } from "@/lib/deliberations";
import { jobFromSseEvent, jobsForProject, upsertJob } from "@/lib/timeline";
import { pickProjectId } from "@/lib/projectSelection";
import AnalyticsRoute from "@/pages/AnalyticsRoute";
import ApprovalsRoute from "@/pages/ApprovalsRoute";
import ReportsRoute from "@/pages/ReportsRoute";
import SuggestionsRoute from "@/pages/SuggestionsRoute";
import TimelineRoute from "@/pages/TimelineRoute";
import type { Approval, BackendReach, Deliberation, Project, SseEvent, Worklist } from "@/types/api";

function backendReach(health: { isPending: boolean; isSuccess: boolean }): BackendReach {
  if (health.isPending) return "checking";
  return health.isSuccess ? "up" : "down";
}

/**
 * App shell. Until the backend is reachable the health probe fails and every
 * view truthfully renders its designed empty state (C-1: no mock APIs).
 */
export default function App() {
  const health = useBackendHealth();
  const backend = backendReach(health);
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [lensOpen, setLensOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [investigationOpen, setInvestigationOpen] = useState(false);
  const [slateReplay, setSlateReplay] = useState(0);
  const consumePendingJob = useCallback(() => setPendingJobId(null), []);
  const paletteTriggerRef = useRef<HTMLButtonElement>(null);
  const paletteReturnRef = useRef<HTMLElement | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    enabled: backend === "up",
  });
  const projectQuery = useQuery({
    queryKey: ["project", selectedProjectId],
    queryFn: () => getProject(selectedProjectId ?? ""),
    enabled: selectedProjectId !== null,
  });
  const approvalsQuery = useQuery({
    queryKey: ["approvals"],
    queryFn: listApprovals,
    enabled: backend === "up",
  });

  useEffect(() => {
    const next = pickProjectId(selectedProjectId, projectsQuery.data ?? []);
    if (next !== selectedProjectId) setSelectedProjectId(next);
  }, [projectsQuery.data, selectedProjectId]);

  const jobs = jobsForProject(projectQuery.data?.jobs ?? [], selectedProjectId);
  const proposedCount = (approvalsQuery.data ?? []).filter(
    (item) => item.status === "proposed",
  ).length;
  const slateId = investigationOpen ? "investigation" : slateForRoute(location.pathname);

  const handleSseEvent = useCallback(
    (event: SseEvent) => {
      if (event.type === "worklist.updated") {
        const payload = event.payload as { worklist?: Worklist };
        if (!payload.worklist || !selectedProjectId) return;
        if (
          payload.worklist.project_id &&
          payload.worklist.project_id !== selectedProjectId
        ) {
          return;
        }
        queryClient.setQueryData(["worklist", selectedProjectId], payload.worklist);
        return;
      }
      if (event.type === "approval.updated") {
        const approval = event.payload as Partial<Approval> & { approval_id?: string };
        if (!approval.approval_id) return;
        queryClient.setQueryData<Approval[]>(["approvals"], (rows) => {
          const current = rows ?? [];
          const existing = current.find((row) => row.approval_id === approval.approval_id);
          if (!existing) return current;
          return current.map((row) =>
            row.approval_id === approval.approval_id ? { ...row, ...approval } : row,
          );
        });
        return;
      }
      const deliberation = deliberationFromSseEvent(event);
      if (deliberation && selectedProjectId) {
        queryClient.setQueryData<Deliberation[]>(
          ["deliberations", selectedProjectId],
          (rows) => upsertDeliberation(rows ?? [], deliberation),
        );
        return;
      }
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

  const openPalette = useCallback(() => {
    paletteReturnRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : paletteTriggerRef.current;
    setPaletteOpen(true);
  }, []);

  const closePalette = useCallback(() => {
    setPaletteOpen(false);
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => {
          if (open) return false;
          paletteReturnRef.current =
            document.activeElement instanceof HTMLElement
              ? document.activeElement
              : paletteTriggerRef.current;
          return true;
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function runCommand(command: PaletteCommand) {
    setPaletteOpen(false);
    if (command.kind === "lens") {
      setLensOpen((open) => !open);
      return;
    }
    if (command.kind === "route") {
      navigate(pathForRouteCommand(command.id));
      return;
    }
    if (command.kind === "job") {
      const jobId = command.id.slice("job:".length);
      navigate("/");
      setPendingJobId(jobId);
    }
  }

  const timeline = (
    <TimelineRoute
      selectedProjectId={selectedProjectId}
      onSelectedProjectIdChange={setSelectedProjectId}
      lensOpen={lensOpen}
      pendingJobId={pendingJobId}
      onPendingJobConsumed={consumePendingJob}
      onInvestigationOpenChange={setInvestigationOpen}
    />
  );

  return (
    <div className="flex h-dvh flex-col bg-bg text-ink">
      <TopBar
        connected={health.isSuccess}
        checking={health.isPending}
        streamEnabled={selectedProjectId !== null}
        sseStatus={sse.status}
        proposedCount={proposedCount}
        onOpenPalette={openPalette}
        onReplaySlate={() => setSlateReplay((token) => token + 1)}
        paletteTriggerRef={paletteTriggerRef}
      />
      <main className="min-h-0 flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={timeline} />
          <Route
            path="/suggestions"
            element={
              <SuggestionsRoute backend={backend} selectedProjectId={selectedProjectId} />
            }
          />
          <Route path="/approvals" element={<ApprovalsRoute backend={backend} />} />
          <Route
            path="/analytics"
            element={
              <AnalyticsRoute
                backend={backend}
                selectedProjectId={selectedProjectId}
                onJumpToJob={(jobId) => {
                  navigate("/");
                  setPendingJobId(jobId);
                }}
              />
            }
          />
          <Route
            path="/reports"
            element={
              <ReportsRoute backend={backend} selectedProjectId={selectedProjectId} />
            }
          />
          <Route path="*" element={timeline} />
        </Routes>
      </main>
      <SlateDeck id={slateId} replayToken={slateReplay} />
      <CommandPalette
        open={paletteOpen}
        commands={allCommands(jobs)}
        returnFocusRef={paletteReturnRef}
        onClose={closePalette}
        onSelect={runCommand}
      />
    </div>
  );
}
