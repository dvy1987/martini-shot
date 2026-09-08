import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import AgentPanel from "@/components/AgentPanel";
import type { Deliberation } from "@/types/api";

afterEach(cleanup);

const deliberation: Deliberation = {
  cycle_id: "cyc-1",
  case_id: "case-1",
  created_at: "2026-09-04T00:00:00Z",
  trigger: { kind: "job_failed", job_id: "job-1", station: "loudness", project_id: "p-1" },
  specialists: ["reliability_investigator", "delivery_qc"],
  verdict: {
    rejected: [{ claim_ref: "doc-x", reason: "stale: the job was re-rendered" }],
    approved_specialists: ["delivery_qc"],
    overall_confidence: "high",
  },
  recommendation: {
    ranked_actions: [
      {
        command_name: "retry_job",
        args: { job_id: "job-1" },
        cost_estimate_micros: 500,
        reversible: true,
        leverage: 0.9,
      },
    ],
    dissent: ["QC and reliability disagree on the retry cost estimate"],
  },
  status: "proposed",
};

describe("AgentPanel", () => {
  it("renders the team's verdict, ranked actions, and dissent from the real deliberation record", () => {
    render(<AgentPanel deliberation={deliberation} />);

    expect(screen.getByText(/How Martini Shot reached this result/i)).toBeInTheDocument();
    expect(screen.getByText(/reliability_investigator/)).toBeInTheDocument();
    expect(screen.getByText(/delivery_qc/)).toBeInTheDocument();
    expect(screen.getByText(/retry job/)).toBeInTheDocument();
    expect(screen.getByText(/Can be undone/i)).toBeInTheDocument();
    expect(screen.getByText(/QC and reliability disagree on the retry cost estimate/)).toBeInTheDocument();
    expect(screen.getByText(/Not used: stale: the job was re-rendered/)).toBeInTheDocument();
  });

  it("says no further action was suggested instead of inventing any", () => {
    const empty: Deliberation = {
      ...deliberation,
      recommendation: { ranked_actions: [], dissent: [] },
      verdict: { rejected: [], approved_specialists: [] },
    };
    render(<AgentPanel deliberation={empty} />);

    expect(screen.getByText(/no further action was suggested/i)).toBeInTheDocument();
    expect(screen.queryByText(/retry job/)).not.toBeInTheDocument();
  });
});
