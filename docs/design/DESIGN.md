# DESIGN.md — Martini Shot frontend design charter

Version: 3 (2026-08-28; v2 progressive reveal + slates · v3 motion system: Framer Motion, Leonardo-grade) · Status: **DECIDED** (owner-approved; produced via first-principles
analysis + adversarial review at owner direction) · **Binding for all frontend work.**

**Brand voice:** the martini shot is the last setup of the shooting day — the one
before wrap is called. The product is the system that calls wrap: every station
locked, every handoff verified, the day accounted for. Demo cold-open line:
*"The martini shot is the last shot of the day. This is the system that calls wrap."*

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
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | reveals, media, spring settle (≤280ms) |
| `--ease-chrome` | `cubic-bezier(0.4, 0, 0.6, 1)` | hovers, toggles 80–140ms |

**Type:** IBM Plex Sans (UI, 13–15px) + JetBrains Mono (timecode, IDs, queries, costs —
mono is a primary voice, not an accent) via `@fontsource`. No Inter. No gradients, no
glassmorphism, no glow — the discipline is the luxury.

**Density:** dense ONLY in the timeline/table data surfaces (32px rows, tight lanes).
Chrome, cards, and drawers stay calm: 16–24px padding, gutters ≥16px, a maximum of
two panels visible beyond the timeline, one inspector at a time. Anything that can
unfold later stays folded (Progressive reveal, below). **Media:** before/after
viewers breathe.

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
typed data, different render. No canvas, no D3. Motion via the v3 Motion system
(Framer Motion), CSS transitions only for trivial hovers.

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

### Stage 1a surfaces (A5 — reuses the established vocabulary; no new visual language)
- **Alternates lane** (Season Timeline): every generated clip appears as an
  alternate attached to its shot — ghost-styled clip cards under the locked one;
  the locked cut is never silently replaced. Add/remove-from-continuity is an
  approval-tracked action rendered in the Screening Room, not a toggler.
- **Revision Room**: script panel beside the timeline — script lines aligned to
  shots (mono, timecode-anchored); a user edit highlights affected spans
  (tungsten edge) and proposes regeneration as alternates. Diff view = folded
  evidence chips (before/after line).
- **Camera Language options**: genre-aware suggestion chips per shot (dolly,
  shaky handheld, Steadicam, locked-off…) with one-line rationale; selecting one
  proposes an alternate. Suggestions are model output and say so.
- **Relight Studio presets**: named lighting setups (floor-lamp practical /
  ambient daylight / overhead ceiling / noir) as a preset row in the drawer;
  the before/after wipe carries the lighting label.
- **Draft-first badge**: every generated artifact carries a state chip
  (draft 360p → in QC → master 1080p); drafts render at draft quality and say so
  (paused-frame truthfulness applies).

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

## Progressive reveal & slates (v2 — the calm rule)

The product teaches itself. Complexity unfolds in layers; the first screen is never
the deepest one. **Overview first, detail on demand** — the mantra for every surface.

**Reveal principles (binding):**
1. **One inspector at a time.** Job detail opens as a right-side drawer over the
   timeline (slide-in 140ms), never a wall of side-by-side panels.
2. **Folded by default:** evidence-chain chips expand on click; station lanes with
   >8 episodes collapse to a summary row with a `+N` chip; cost heat-ticks appear on
   hover, not always-on.
3. **Power tools hide until asked:** filters/legend live behind one "Lens" button;
   keyboard hints reveal when ⌘K opens.
4. **Staggered entrance:** lanes fade-slide in with 20ms increments — first load
   only, ≤200ms total, then never again that session.
5. **Empty beats cluttered:** a panel with no data renders its designed empty state,
   not a row of disabled controls.
6. **Text budget:** card body ≤2 lines with expand; numbers in mono, units in captions.

### Slates (educational carousels, film-native)
Name: **slates** — title-card-style explainers. Full-screen scrim `rgba(11,11,13,0.72)`
with a centered 640px `--surface-2` card (1px `--line` border): diagram area (pure
SVG/CSS in brand tokens), plain-language caption + film term, step dots (tungsten
active), `Skip` top-right, `Next →` bottom-right with kbd hints (← → navigate,
Esc closes). Scrim click closes — **never blocks the app behind it**. Completion is
remembered per-slate in `localStorage` (`pc.seen.<id>`); a small ghost `?` on complex
card headers reopens that slate on demand.

| Slate | When | Slides |
|---|---|---|
| `welcome` | first visit | 1) "This is the lab" — timeline anatomy · 2) "Your supervisor never sleeps" — markers & approvals · 3) "Every claim is clickable" — evidence philosophy |
| `investigation` | first Investigation Card | alert → evidence → verdict → action anatomy in 4 beats |
| `accounting` | first Spend Control escalation | "Why is my station paused?" — throttle/stop/approve |
| `dailies` | first morning report | how verdicts cite their evidence |

Every slate diagram is labeled in plain language first, film term second — same rule
as the status vocabulary. Slates are demo assets: skippable in one Esc, and slide 1
of each is a composed shot worth showing in the video.

**Delight within discipline:** micro-moments only — the live UTC clock ticks its
seconds in mono, clip hover lifts 1px with a soft elevation shadow, the connection
pill breathes once on reconnect. No confetti, no glow, no cartoon bounce; the luxury
is restraint, spacing, and typography doing their jobs. Where animation earns its
place, see the Motion system (v3).

## Motion system (v3 — Leonardo-grade, disciplined)

Library: **Framer Motion** (`motion` package) — chosen over GSAP for React-native
`AnimatePresence`/layout primitives (drawer mount/unmount, list transitions, slate
choreography) and bundle size. ONE motion stack; GSAP joins only if a sequenced
timeline scrub is ever required (not v1). Wrap the app in `<MotionConfig
reducedMotion="user">`.

**Inventory (each entry earns its place):**
- Drawer inspector: spring mount/unmount, 200ms, one damped oscillator curve reused
  product-wide; scrim fades 120ms.
- Timeline clips: status changes animate color/edge (layout animation); a new clip
  enters 0.96→1 scale + fade; SSE edge updates glide, never jump or bounce.
- Markers (⚑): tungsten pulse 2s loop; pauses while its drawer is open.
- Evidence chips: height-expand on click; query result numbers **roll up**
  (count-up ~400ms) on first expand; cost figures count up in mono when a job opens.
- Screening Room: draggable **before/after wipe** with a 1px tungsten hairline and
  reveal-curve release — the Pickups money shot, also a demo beat.
- Slates: scrim fade → card lift 8px + fade; diagrams **draw on** (SVG
  pathLength ~400ms); slide crossfade 160ms; dots slide.
- Skeletons→content: crossfade + 8px rise, 30ms stagger per row.
- Lane staggered entrance (v2) implemented with Framer stagger, first load only.
- Rendering state inside a clip: 1.2s shimmer sweep (`--surface-2`→`--line`→`--surface-2`).
- Connection pill: status crossfade + single breath on reconnect (v2 rule stands).

**Rules (binding):** animation never carries information alone (a paused frame is
truthful); entrance/exit ≤280ms; the ONLY loops are marker pulse, pill breath, and
clip shimmer; no animation on first paint of tables (data must be instant);
`prefers-reduced-motion` swaps to instant state changes; hidden-tab animations pause.

## Demo-legibility rules
Min body 13px at 1080p; mono ≥12px. APCA Lc ≥ 60 for text on `--bg` (verify with a
checker; muted text only for non-essential metadata). One idea per screen region.
Animation never carries information alone (live state must survive a paused frame).

## Anti-patterns (banned even if instinct says otherwise)
Purple→pink gradients · Tailwind default palette · Inter-only typography · glassmorphism
· glow · cartoon-bounce overshoot (one damped spring curve is allowed, no oscillation)
· chat-style agent panel · generic SaaS sidebar landing · lorem ipsum or placeholder
data · emoji in UI copy · stock illustrations · two animation stacks · light mode as
default (dark is the product; light is a later fallback, not v1 scope).

## Build sequencing (protects the floor)
v1 floor = spec §7 console (tables + drill-ins, polished) — guaranteed shippable.
Flagship layer = timeline lanes + investigation cards on the SAME typed API model.
Both consume one client module; the flagship is additive, never a rewrite.
