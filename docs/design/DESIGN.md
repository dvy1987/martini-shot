# DESIGN.md — Post Command frontend design charter

Version: 1 (2026-08-28) · Status: **DECIDED** (owner-approved; produced via first-principles
analysis + adversarial review at owner direction) · **Binding for all frontend work.**

## Decision in one sentence
A dark, film-lab-precise ops console whose core object is the **Season Timeline** —
stations as lanes, jobs as clips, faults as markers — where every agent claim is
clickable evidence and human attention is spent only on exceptions.

## Why (reasoning that survived review)

**Fundamental truths (kept):**
1. **Evidence is the content.** C-4.3 makes the audit trail the product. Every agent
   claim on screen renders its proof (query, span, annotation) and links into Grafana —
   verification is one click away. This is also the write-path MCP demo.
2. **The domain owns a precise visual language.** Timecode, lanes, reels, stems, LUFS.
   Using it fuses observability × media *inside the UI* — the idea-quality
   differentiator — and signals theme fit without a word of copy.
3. **Batch scale reads as shape, never rows.** 9 episodes × ~30 languages × 16 stations
   is only legible as a timeline/heatmap surface (mission §7: "a working system, not a
   20-row list").
4. **The user's job is exception handling.** Healthy = calm. Markers + approvals pull
   attention; nothing else competes for it.
5. **The demo is 1080p video at ~25 s per beat.** Size, contrast, and motion discipline
   are hard constraints (see Demo-legibility rules).

**Conventions discarded (and why):**
- "Look like Grafana" → judges live in Grafana; imitation competes with the host and
  every other entry. We **link** to Grafana, we don't imitate it.
- "Agent = chat panel" → invites unscripted demos and ChatGPT comparisons. The
  investigation is a **case file**; interaction happens through **Approvals**.
- "SaaS sidebar + list-page landing" → wastes the money moment. The landing IS the
  timeline; secondary views live behind the command bar and compact drawers.
- "Generic dark theme + accent color" → identity comes from the DI-suite surface +
  film-native information design, not a color wash.

## Visual system

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0B0B0D` | app background (DI-suite near-black, hint of warmth) |
| `--surface-1/2` | `#121316` / `#17181C` | panels / raised cards |
| `--line` | `#232529` | 1px borders, lane separators |
| `--text` | `#E8E6E1` | primary text (warm off-white) |
| `--text-muted` | `#A8A6A0` | metadata (≥13px only) |
| `--tungsten` | `#E8A33D` | **human-attention accent**: faults, approvals, focus |
| `--signal` | `#3FB68B` | locked / pass / healthy (desaturated green) |
| `--agent` | `#5B7FDB` | agent-driven actions (machine, calm) |
| `--danger` | `#D9544F` | genuine failures ONLY (never decorative) |
| `--radius` | 4–6px | inputs and cards; nothing rounder |
| `--dur-chrome` | 80–140ms, `cubic-bezier(0.4, 0, 0.6, 1)` | all UI motion; mechanical, no bounce |
| `--dur-media` | ≤260ms, `cubic-bezier(0.16, 1, 0.3, 1)` | media reveals only (before/after, dailies) |

**Type:** IBM Plex Sans (UI, 13–15px) + JetBrains Mono (timecode, IDs, queries, costs —
mono is a primary voice, not an accent) via `@fontsource`. No Inter. No gradients, no
glassmorphism, no glow — the discipline is the luxury. **Density:** dense chrome
(32px table rows, tight lanes), generous media (before/after viewers breathe).

## Information architecture

- **Top bar (always):** project title · live UTC clock · SSE connection pill
  (live / reconnecting / backend unreachable) · approvals badge · ⌘K hint.
- **Landing `/` = Season Timeline** (full-bleed, see flagship components).
- Routes: `/projects/:id` timeline · `/projects/:id/jobs/:jobId` job detail ·
  `/approvals` screening room · `/reports` dailies (morning report) · settings drawer.
- **⌘K command bar (mandatory):** jump-to-fault, open episode/station, approve
  proposed, toggle table view. Keyboard-first — the demo operator drives by keyboard.

## Flagship components

### Season Timeline
CSS-grid lanes (one per station), episodes as rows within the lane, jobs as clip-like
blocks: width ∝ duration, color = status, cost as a subtle right-edge heat tick.
Faults render as **markers** (⚑ glyph, tungsten, slow pulse ≤2s). Live SSE updates
animate a block's edge, never bounce. A **table-fallback toggle** ships in v1 — same
typed data, different render. No canvas, no D3.

### Investigation Card (the case file, not chat)
1. **Alert** — what fired: metric, value, timestamp (timecode-styled), threshold.
2. **Evidence chain** — the agent's actual queries as slate chips (PromQL / LogQL /
   Tempo), each expandable to returned data and linking into the Grafana panel.
3. **Verdict** — one plain sentence: severity + root cause.
4. **Proposed action** — retry (strengthened anchors) / re-time / block shipment /
   throttle station, with cost estimate (micro → `$0.0042`).
5. **State line** — proposed → approved → acting → resolved, citing the Grafana
   annotation/incident ID at each step.

### Screening Room (approvals)
Side-by-side before/after viewer (the Pickups money shot), cost delta, one-click
approve/reject with reason. Spend Control escalations land here under a red
"PRODUCTION ACCOUNTING" slate — governance with a sense of humor that stays factual.

### Dailies (morning report)
The report as a dated contact-sheet: headline verdicts per station, citations
(linking to evidence), embedded Grafana panel links. Readable in 20 seconds on video.

### Status vocabulary (film-native mapping, 1:1 with the job state machine)
| State | Term | Glyph | Color |
|---|---|---|---|
| queued | In bin | ● | muted |
| running | In the lab | ▶ | agent |
| pass | Locked | ◼ | signal |
| fail | Failed QC | ⚑ | danger |
| quarantined | Vaulted | ◇ | tungsten |
| needs_human | Flagged | ⚑ | tungsten |
| throttled | Held by accounting | ⏸ | tungsten |

Every film term gets a plain-language subtitle on first appearance.

## States (honest — C-1.*)
Loading = skeletons in lane/table shape (never spinners alone). Empty = designed
surfaces that say what is awaited ("Awaiting first turnover — ingest hasn't run").
Error = the `{code, message}` envelope, a retry affordance, never a raw stack trace.
The connection pill is truthful about backend reachability at all times.

## Demo-legibility rules
Min body 13px at 1080p; mono ≥12px. APCA Lc ≥ 60 for text on `--bg` (verify with a
checker; muted text only for non-essential metadata). One idea per screen region.
Animation never carries information alone (live state must survive a paused frame).

## Anti-patterns (banned even if instinct says otherwise)
Purple→pink gradients · Tailwind default palette · Inter-only typography · glassmorphism
· glow · bouncy springs · chat-style agent panel · generic SaaS sidebar landing · lorem
ipsum or placeholder data · emoji in UI copy · stock illustrations · light mode as
default (dark is the product; light is a later fallback, not v1 scope).

## Build sequencing (protects the floor)
v1 floor = spec §7 console (tables + drill-ins, polished) — guaranteed shippable.
Flagship layer = timeline lanes + investigation cards on the SAME typed API model.
Both consume one client module; the flagship is additive, never a rewrite.
