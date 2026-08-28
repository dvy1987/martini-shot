/** Typed endpoint functions — the working contract until the backend OpenAPI lands. */

import { apiFetch, apiBaseUrl } from "@/api/client";
import type { Approval, Job, MorningReport, Project, Settings } from "@/types/api";

export function projectEventsUrl(projectId: string): string {
  return `${apiBaseUrl}/api/v1/projects/${encodeURIComponent(projectId)}/events`;
}

export function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/api/v1/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/api/v1/projects/${encodeURIComponent(projectId)}`);
}

export function getJob(jobId: string): Promise<Job> {
  return apiFetch<Job>(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
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

export function getSettings(): Promise<Settings> {
  return apiFetch<Settings>("/api/v1/settings");
}

export function updateSettings(settings: Settings): Promise<Settings> {
  return apiFetch<Settings>("/api/v1/settings", {
    method: "PATCH",
    body: JSON.stringify(settings),
  });
}
