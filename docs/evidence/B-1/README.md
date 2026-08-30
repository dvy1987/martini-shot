# B-1 Evidence — ADK supervisor scaffold (plan B-1)

Date: 2026-08-30 · RED observed (ImportError) → GREEN, 7/7.

## DoD verification — tool registry + autonomy toggle + persona wiring
| Requirement | Proof |
|---|---|
| tool registry | `test_registry_registers_and_lists_tools`, `test_registry_rejects_duplicates_and_unknown` — single source of truth for agent capabilities; duplicate/unknown rejected |
| autonomy toggle, propose-only DEFAULT | `test_autonomy_defaults_to_propose_only`; `test_autonomy_act_mode_requires_explicit_env` (POST_COMMAND_AUTONOMY=act; garbage value → ValueError) |
| act tools blocked in propose-only | `test_act_tools_are_blocked_in_propose_only` — refusal reason names propose-only mode; `test_read_tools_allowed_in_propose_only` |
| persona + model + ADK wiring | `test_build_supervisor_wires_persona_model_and_tools` — a REAL `google.adk.agents.LlmAgent` named `post_supervisor`, model == pinned TEXT_MODEL, instruction contains "Post Supervisor", ≥1 real tool bound |

## Design notes
- Seed tools are REAL (C-1.2): `read_job`/`list_failed_jobs` read the real Firestore lease queue; `retry_job` is registered as act-class and gated (wiring to the queue lands later — raising, not mocked).
- In propose-only mode act tools are excluded from the ADK toolset AND refused by `Autonomy.check` at the boundary (defense in depth).
- Model pinning via `backend/core/models.py` TEXT_MODEL only (ADR-0002).
- No network calls in tests: agent assembly is construction-only; Firestore reads are real but free-tier.
