# ADR 0002: Model & SDK toolchain pinning (owner ruling 2026-08-28)

Date: 2026-08-28 | Status: Accepted | Deciders: agent (owner-mandated directives)

## Context

Owner directives: use the latest Google ADK and Gen AI SDKs; use **Gemini 3.7
Flash at high reasoning for every text-LLM task**; use the latest Google media
models (Omni, Veo) generously; compute on Vertex AI (GCP credits) with the AI
Studio API as per-model fallback.

## Decision

### Model routing (all via `google-genai` client)

| Task class | Model | Config |
|---|---|---|
| **ALL text-LLM reasoning** — supervisor investigation chains, morning report, camera-work suggestions, script alignment, rubric judges, fix proposals | `gemini-3.7-flash` | **thinking level HIGH** (+ thought summaries for the audit trail) |
| Video generation & conversational editing | `gemini-omni-1.1-flash-preview` | Interactions API; stateful multi-turn via `previous_interaction_id`; tasks: edit/extend/image_to_video/reference_to_video; resolution 360p (draft) → 1080p (master) |
| Precision video extension / first-last-frame | `veo-3.1` | used where Omni's extension needs frame-exact anchors; Omni-vs-Veo decided per-op by eval (JSONL evidence) |
| Dub voices (3 languages) | Chirp 3 HD via Cloud Text-to-Speech | SSML pacing; duration-delta measured by S4 |
| Video understanding (script extraction, content QC, scene analysis) | `gemini-3.7-flash` | video input, thinking high |
| Stills / anchor frames (if needed) | Imagen / Nano Banana via genai SDK | fallback only; frame extraction via ffmpeg preferred |

### SDK / runtime pinning (Python ≥ 3.12; dev machine 3.13.7)

| Package | Pin | Why |
|---|---|---|
| `google-genai` | `==2.20.0` | latest (2026-08-25); ADK 2.8.0 requires `>=2.19,<3` — do NOT upgrade to 3.x until ADK declares compatibility (SDK warns of breaking AFC changes in 3.0) |
| `google-adk` | `==2.8.0` | latest stable (2026-08-26); ADK 2.0 Workflow/Task API |
| FastAPI / uvicorn | `>=0.133` / `>=0.34` | ADK 2.8.0 floors |
| OTel SDK | `>=1.39,<=1.42.1` | ADK floor; `opentelemetry-instrumentation-google-genai>=0.7b1` for AI Observability (B-3) |
| GCP clients | firestore `>=2.11,<3` · storage `>=2.18,<4` · secret-manager `>=2.22,<3` · texttospeech `>=2.37` | ranges respect ADK 2.8.0 constraints |

### Runtime selection

- **Primary: Vertex AI / Gemini Enterprise Agent Platform** — `genai.Client(enterprise=True, project=PROJECT, location=global)` with ADC (owner's GCP credits; $300 available).
- **Fallback: AI Studio Gemini API** — `genai.Client(api_key=...)` per model, only where the G0 probe shows Vertex lags (recorded in `docs/evidence/G0/`).
- Media processing: ffmpeg 9.0.1 (winget, dev machine); the same pinned version family ships in the Cloud Run image (A-4).

## Consequences

- SDK upgrades are an eval-gated decision (C-3): bump `google-genai` major only after re-running the G0 spike + EDD suites.
- Every text-LLM call records thinking summaries into logs/traces — doubles as the judge-facing audit trail (C-4).
- Model IDs are centralized in `backend/core/models.py` (built with A-1) — never hard-coded in station modules.

## References

- google-genai 2.20.0 (PyPI, 2026-08-25) · google-adk 2.8.0 (PyPI, 2026-08-26)
- Gemini API docs: video/Omni (ai.google.dev/gemini-api/docs/omni), thinking (…/docs/thinking), latest-model (Gemini 3.7 Flash)

## G0 probe verification (2026-08-28, docs/evidence/G0/capability_probe.json)

- `gemini-3.7-flash` thinking HIGH: **callable on Vertex** (`martini-shot`, global); thought summaries confirmed (include_thoughts=True).
- Omni: Vertex serves the **`-preview`** suffixed ID only — pin updated from `gemini-omni-1.1-flash` to `gemini-omni-1.1-flash-preview`.
- Veo: absent from `models.list` (expected; separate API surface). Direct-call verification happens in the quality spike before any Veo reliance.
- Cloud TTS: **2,066 voices, 1,598 Chirp HD** available. ADC quota project set to `martini-shot`.
