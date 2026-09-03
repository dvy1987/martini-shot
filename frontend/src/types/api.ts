/** Domain types for the /api/v1 contract (see docs/specs §7, frontend/AGENTS.md). */

export type JobStatus =
  | "queued"
  | "running"
  | "pass"
  | "fail"
  | "quarantined"
  | "needs_human"
  | "throttled";

export type ProjectHealth = "healthy" | "degraded" | "failing";

export interface Project {
  project_id: string;
  title: string;
  created_at: string;
  station_counts: Record<string, number>;
  health: ProjectHealth;
  jobs?: Job[];
}

export interface Job {
  job_id: string;
  station: string;
  project_id: string;
  input_refs: string[];
  status: JobStatus;
  attempts: number;
  cost_micros?: number;
  error?: { code: string; message: string } | null;
  checksum_sha256?: string | null;
}

export type SseEvent =
  | { type: "job.updated"; payload: { job: Job }; at: string }
  | { type: "approval.updated"; payload: Partial<Approval>; at: string }
  | {
      type: "incident.opened";
      payload: { incident_id: string; job_id?: string; severity: string; title: string };
      at: string;
    }
  | { type: "annotation.created"; payload: { annotation_id: string; job_id?: string }; at: string }
  | { type: string; payload: unknown; at: string };

export type ApprovalKind = "fix" | "spend";
export type ApprovalStatus =
  | "proposed"
  | "approved"
  | "rejected"
  | "acting"
  | "resolved"
  | "failed";

export interface Approval {
  approval_id: string;
  project_id: string;
  job_id?: string;
  kind: ApprovalKind;
  title: string;
  detail?: string;
  before_url?: string;
  after_url?: string;
  cost_delta_micros?: number;
  created_at: string;
  status: ApprovalStatus;
  result?: Record<string, unknown> | null;
  approver?: string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  sweep_retries?: number | null;
}

export interface ReportVerdict {
  station: string;
  verdict: string;
  summary: string;
  evidence_url?: string;
  cost_micros?: number;
}

export interface MorningReport {
  date: string;
  generated_at: string;
  verdicts: ReportVerdict[];
}

export type Autonomy = "propose_only" | "act_with_approval" | "autonomous";

export interface Settings {
  autonomy: Autonomy;
}

export type BackendReach = "checking" | "up" | "down";

export interface ApiErrorBody {
  error: { code: string; message: string };
}
