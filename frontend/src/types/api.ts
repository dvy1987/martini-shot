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
  | { type: "deliberation.completed"; payload: Deliberation; at: string }
  | { type: string; payload: unknown; at: string };

/** H-1f: one multi-agent deliberation cycle (real pc-deliberations doc). */
export interface RankedAction {
  command_name: string;
  args: Record<string, unknown>;
  cost_estimate_micros: number;
  reversible: boolean;
  leverage?: number;
}

export interface Deliberation {
  cycle_id: string;
  case_id: string;
  created_at: string;
  trigger: { kind?: string; job_id?: string; station?: string; project_id?: string };
  specialists: string[];
  verdict: {
    rejected?: { claim_ref: string; reason: string }[];
    approved_specialists?: string[];
    overall_confidence?: string;
  };
  recommendation: { ranked_actions?: RankedAction[]; dissent?: string[] };
  status: string;
}

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

/** H-0b autonomy toggle: one flip, no redeploy (pc-control/settings). */
export type Autonomy = "propose_only" | "act";

export interface Settings {
  autonomy: Autonomy;
  /** Nightly supervisor envelope, integer micros (default $20 = 20_000_000). */
  post_command_budget_micros: number;
}

export type BackendReach = "checking" | "up" | "down";

export interface ApiErrorBody {
  error: { code: string; message: string };
}

/** AL-1 / Stage 1a: every generated clip is an ALTERNATE on its shot. */
export interface Alternate {
  alternate_id: string;
  op?: string | null;
  artifact_ref?: string | null;
  eval_scores?: Record<string, number> | null;
  tier?: "draft" | "master" | string | null;
  status?: "draft" | "continuity" | "retired" | (string & {}) | null;
  created_at?: string | null;
}

export interface SceneUnderstanding {
  ingested?: boolean | null;
  spoken_words?: string | null;
  has_speech?: boolean | null;
  scene?: string | null;
}

/** Row of GET /api/v1/projects/{id}/shots (alternates embedded). */
export interface ShotRow {
  shot_id: string;
  title?: string | null;
  locked: boolean;
  locked_by?: string | null;
  current_alternate_id?: string | null;
  created_at?: string | null;
  scene_understanding?: SceneUnderstanding | null;
  alternates: Alternate[];
}

/** GET /api/v1/alternates/{id}/media — real GCS V4 signed URL. */
export interface AlternateMedia {
  alternate_id: string;
  url: string;
  expires_in_minutes: number;
}

export type InspectImpact = "none" | "low" | "medium" | "high";
export type InspectKind = "none" | "defect" | "improvement";
export type InspectStatus = "empty" | "ok" | "needs_work";

export interface InspectNote {
  station: string;
  agent: string;
  status: InspectStatus;
  impact: InspectImpact;
  kind: InspectKind;
  summary: string;
  cost_estimate_micros: number;
  shot_id?: string;
}

export interface WorklistItem {
  id: string;
  station: string;
  status: string;
  impact?: InspectImpact;
  kind?: InspectKind;
  summary?: string;
  job_id?: string;
  shot_id?: string;
  blocked_by?: string[];
}

export interface Worklist {
  project_id: string;
  budget_micros: number;
  spent_micros: number;
  status: string;
  attendance: InspectNote[];
  items: WorklistItem[];
  final_refs: string[];
  original_refs: string[];
  rank_reason?: string;
}
