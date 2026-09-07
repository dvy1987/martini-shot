/** Typed endpoint functions — the working contract until the backend OpenAPI lands. */

import { apiFetch, eventsUrl } from "@/api/client";
import type {
  AlternateMedia,
  Approval,
  Deliberation,
  Job,
  MorningReport,
  Project,
  Settings,
  ShotRow,
  Worklist,
} from "@/types/api";

export function projectEventsUrl(projectId: string): string {
  return eventsUrl(`/api/v1/projects/${encodeURIComponent(projectId)}/events`);
}

export function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/api/v1/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/api/v1/projects/${encodeURIComponent(projectId)}`);
}

export function ingestClip(projectId: string, file: File): Promise<Job> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<Job>(`/api/v1/projects/${encodeURIComponent(projectId)}/ingest`, {
    method: "POST",
    body,
  });
}

export function getJob(jobId: string): Promise<Job> {
  return apiFetch<Job>(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
}

export function listDeliberations(projectId: string, jobId?: string): Promise<Deliberation[]> {
  const query = jobId ? `?job_id=${encodeURIComponent(jobId)}` : "";
  return apiFetch<Deliberation[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/deliberations${query}`,
  );
}

export function listApprovals(): Promise<Approval[]> {
  return apiFetch<Approval[]>("/api/v1/approvals");
}

/** Stage 1a alternates lane: shots with their alternates embedded (one call). */
export function listProjectShots(projectId: string): Promise<ShotRow[]> {
  return apiFetch<ShotRow[]>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/shots`,
  );
}

/** Signed media URL (60 min) — fetched on demand, never eagerly. */
export function getAlternateMedia(alternateId: string): Promise<AlternateMedia> {
  return apiFetch<AlternateMedia>(
    `/api/v1/alternates/${encodeURIComponent(alternateId)}/media`,
  );
}

export function decideApproval(
  approvalId: string,
  decision: "approve" | "reject",
  reason?: string,
): Promise<Approval> {
  return apiFetch<Approval>(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`,
    { method: "POST", body: JSON.stringify({ decision, reason }) },
  );
}

export function getMorningReport(projectId: string, date: string): Promise<MorningReport> {
  return apiFetch<MorningReport>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/reports/morning?date=${encodeURIComponent(date)}`,
  );
}

export function proposeCorrection(
  shotId: string,
  body: {
    source_uri: string;
    intent: string;
    protected_subjects?: string[];
    continuity_constraints?: string[];
    reason?: string;
  },
): Promise<{
  approval_id: string;
  status: string;
  agent?: { name: string; decision: string; rationale: string; cost_micros: number };
}> {
  return apiFetch(`/api/v1/shots/${encodeURIComponent(shotId)}/correct`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function proposeExtend(
  shotId: string,
  body: {
    source_uri: string;
    reason?: string;
    prompt?: string;
  },
): Promise<{ approval_id: string; status: string }> {
  return apiFetch(`/api/v1/shots/${encodeURIComponent(shotId)}/extend`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function proposeMaster(
  shotId: string,
  body: {
    op: string;
    source_uri?: string;
    reason?: string;
    intent?: string;
    preset?: string;
    angle?: string;
    movement?: string;
  },
): Promise<{ approval_id: string; status: string }> {
  return apiFetch(`/api/v1/shots/${encodeURIComponent(shotId)}/master`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSettings(): Promise<Settings> {
  return apiFetch<Settings>("/api/v1/settings");
}

export function updateSettings(settings: Settings): Promise<Settings> {
  return apiFetch<Settings>("/api/v1/settings", {
    method: "PATCH",
    body: JSON.stringify(settings),
  });
}

export function startFinish(
  projectId: string,
  budgetMicros = 50_000_000,
): Promise<Worklist> {
  return apiFetch<Worklist>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/finish`,
    { method: "POST", body: JSON.stringify({ budget_micros: budgetMicros }) },
  );
}

export function getWorklist(projectId: string): Promise<Worklist> {
  return apiFetch<Worklist>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/worklist`,
  );
}

export function patchWorklist(projectId: string, order: string[]): Promise<Worklist> {
  return apiFetch<Worklist>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/worklist`,
    { method: "PATCH", body: JSON.stringify({ order }) },
  );
}
