# AO "Post Command" — Complete Mission Briefing & Station Map

**Read this file first.** It is the single self-contained context document for our
hackathon project. Anyone (human or agent) who reads only this file should fully
understand what we are building, why, how we got here, and what happens next.
Last updated: **2026-08-26**. Companion file: `IDEAS.md` (full idea catalog, 51 ideas).

---

## 1. What we are doing (the mission)

We are entering the **Agentic Cinema hackathon** (Google Cloud × Devpost,
"Agentic Cinema: The Blockbuster Hackathon"), submitting to the **Grafana Labs
partner track**. Deadline: **September 9, 2026, 2:00 PM PT** — as of this update,
**14 days remain**. Full original brief: `docs/agentic-cinema.md`.
Distilled rules: `docs/grafana-track-notes.md`.

Deliverables required by the rules:

1. A working web-hosted project (public URL).
2. A public open-source repo created during the contest window, with an OSI
   license visible at repo top, demonstrating Google Cloud AND Grafana usage
   *in code* (`google-adk` / `google-genai` etc., imported and called).
3. A ≤3-minute English demo video on YouTube/Vimeo showing real functioning.
4. Team size ≤ 4. New project only (nothing derived from pre-contest work).

Judging (equal weights): Technological Implementation · Design · Potential
Impact · Quality of the Idea. Stage One is a pass/fail screen (requirements +
theme fit); Stage Two scores against those four criteria.

---

## 2. What the Grafana track is (and what it demands)

Grafana Labs makes the observability stack: dashboards, metrics (Prometheus/
Mimir), logs (Loki), traces (Tempo), alerting/IRM (OnCall). For this hackathon
they expose the **Grafana Cloud MCP server** — an endpoint
(`https://mcp.grafana.com/mcp`) exposing **60+ tools** an AI agent can call:
query metrics (PromQL), query logs (LogQL), search traces (Tempo), search
dashboards, generate dashboard links, write annotations, manage alerts and
incidents. Auth is OAuth via one-time browser authorization (~30-day refresh);
for headless runs there is the open-source `grafana/mcp-grafana` server with a
service-account token.

**Hard track rule:** the project must *actively use* the Grafana stack at runtime
through that MCP server. Merely mentioning Grafana, or using their "AI
Observability" monitoring alone, does NOT qualify — the MCP connection is what
judges check. Recommended bonus: instrument our own agent with Grafana Cloud AI
Observability (OpenTelemetry SDKs) so token cost / latency / tool calls appear in
Grafana during the demo — the agent literally observes itself while observing.

**AI restriction:** all AI/agent work must be Google (Gemini models, ADK, Vertex
AI / Agent Engine). No OpenAI/Anthropic/AWS/Microsoft AI. Non-AI tooling
(ffmpeg, OpenCV, hosting, DBs) is unrestricted.

**Theme lock:** the project must solve a bottleneck across the entertainment &
media value chain, targeting **filmmakers, screenwriters, studio crews, or fans**
(official rules wording). Pure DevOps tools with no media angle fail screening.

---

## 3. How we started (the journey, condensed)

Understanding the path matters because every turn left residue in the final idea.

1. **Batch 1–2 (ops-flavored ideas):** render farms, broadcast control rooms,
   LED volumes, dailies pipelines. Owner rejected all — too "SRE pain," no spark.
2. **Batch 3–4 (pattern break):** ticket drops, esports, escape rooms, theme
   parks, AI production lines (Q), night-shift AI supervisors (R). Still no hit,
   but Q and R later became ingredients.
3. **Owner question: "Ben Affleck's startup?"** Research surfaced **Artists
   Equity** (Affleck/Damon's fair-share studio — crew share film profits; needs
   trustworthy performance numbers). Mined for ideas AD/AE/AF. Owner pushed
   deeper; correction discovered they are NOT a post/VFX company — which led to
   the real target: **InterPositive**, Affleck's AI-filmmaking-tools startup
   (soundstage-trained model fixing backgrounds/lighting/missing shots,
   technique-only guardrails), acquired by **Netflix for $587M in March 2026**.
   Signal: governed AI-assisted film production is industry consensus now.
4. **Market research request:** interactive storytelling products. Finding:
   micro-drama apps (ReelShort etc.) are exploding (~$700M quarterly revenue,
   tripling YoY); branching itself stays niche. Produced AL (micro-drama factory
   watchdog) and killed any temptation to build an interactive story product.
5. **The Diverge reveal:** owner shared their own prior project
   (`github.com/dvy1987/Diverge`, March 2026) — an 8-agent ADK storytelling
   pipeline (Gemini interleaved text+image, TTS, character bibles, Cloud Run).
   Two consequences: (a) Diverge itself is INELIGIBLE (predates contest window),
   (b) it proves the owner can solo-build exactly this stack, and its README
   documents the exact failure modes (character drift, retry loops, latency
   regressions) our ideas described. Synthesis attempt AM ("Storyland Studio
   Ops") followed.
6. **Theme-fit challenge:** owner correctly challenged AM as possibly not a
   "real media workflow." Verdict: defensible with strict framing but
   theme-exposed. This pushed toward concrete artifacts.
7. **Owner's own idea (the turning point):** AI-assisted editing of EXISTING
   footage — background swap, relight, green-screen-without-green-screen,
   camera-angle change. Became **AN "Virtual Pickups"** (with honest scoping:
   true novel camera angles are not feasible with public Google APIs; replaced
   by outpaint-reframing which is feasible and maps to real social-versioning
   work). AN became the leading single idea.
8. **Platform synthesis:** owner asked to think bigger — cover ALL of
   post-production, wrapping AN plus many catalog ideas, adding agentic
   workflows per job until submission. Resolved into **AO "Post Command"** with
   explicit scope discipline so breadth doesn't kill us.
9. **Gap analysis sweep (Aug 25–26):** mapped ALL catalog ideas onto AO,
   found 7 missing real-world post phases (turnovers, dialogue/ADR, loudness,
   cue sheets, conform, trailer QC, archive), added them as AP–AV, built the
   three sequencings below, and drafted the frozen scope awaiting sign-off.

---

## 4. What AO "Post Command" actually is

**One-sentence pitch:** a control room where a film project travels through
post-production as instrumented jobs, watched end-to-end by an AI supervisor
agent that reads all telemetry through the Grafana Cloud MCP server, catches
failures at every station, diagnoses root causes, and drives fixes.

- **Persona (single, real):** the **Post Supervisor** — the actual human job
  that shepherds a project through post handoffs today using spreadsheets,
  email threads, and hope. We give them one cockpit.
- **Core mechanic:** every station runs work as JOBS; every job emits traces,
  metrics, logs (OpenTelemetry → Grafana Cloud). The supervisor agent consumes
  these through Grafana MCP tools: investigates firing alerts, correlates
  logs↔traces↔metrics, writes dashboard annotations as evidence, manages IRM
  incidents, links humans back into Grafana for review.
- **The spine (built once, ~70% of effort):** job runner → OTel instrumentation
  → Grafana MCP agent loop → review UI with a project timeline. Each additional
  station after the spine costs roughly a day, not a week.
- **Hero station:** Virtual Pickups (generative picture fixes) — the deepest,
  flashiest, most 2026-native part of the demo.
- **Why it can win:** maximal legitimate Google surface (ADK orchestration +
  Gemini multimodal QC + Vertex/Cloud Run), maximal legitimate Grafana surface
  (all six MCP tool families used meaningfully), a real named audience
  (studio crews/post supervisors), a playable artifact at the end of the demo,
  and a story nobody else at this hackathon will tell.

---

## 5. The composite ideas/stations (each one explained)

Stations marked ★HERO get deep agentic treatment; THIN ones share the spine and
use deterministic checks; MED are middleweight. Sources point back to catalog IDs.

| # | Station | Source | Tier | World / pain / what the agent does |
|---|---|---|---|---|
| 0 | Handoff Validator | NEW (gap) | silent-in-spine | Locked cuts ship to sound/VFX/color with manifests (EDL/AAF, count sheets); files go missing constantly. Verifies manifest vs delivered files; annotates discrepancies. Runs invisibly inside the spine. |
| 1 | Ingest & Dailies Watchdog | B | thin-med | Overnight footage processing fails silently at 3am; discovered at 7am with half-empty bins. Watches arrival/integrity/sync; catches stalls mid-night; annotates the dailies board. |
| 2 | Edit-Assist & Continuity | AK | med (v2 if tight) | Continuity errors (glass full→empty) slip past one exhausted script supervisor into locked cuts; fans make viral compilations. Monitors automated scene-comparison checks; triages severity/visibility. |
| 3 | **Virtual Pickups** ★ | AI+AN merged | HERO | Reshoot days cost six figures; generative repair now possible (Netflix paid $587M proving it). Editor marks problems ("flat sky", "need vertical", "make it dusk"); jobs run isolate→transform→QC. Agent watches per-op cost/duration AND a classically-computed **flicker/drift score** between frames; flags threshold breaches; auto-retries with anchored prompts; enforces the technique-only consent line (never touches facial performance regions — AJ/X folded in); annotates before/after evidence on the delivery dashboard. Ops: background swap ✅, outpaint reframing 16:9↔9:16 ✅, relight ⚠️ stretch (demote to detect-and-flag if unstable). |
| 4 | Restoration | K | thin-med (v2 default) | Old films scanned/cleaned frame-by-frame by multi-day automated jobs that fail quietly halfway. Treats restoration as a journey; stall/anomaly detection; "minute 43 went wrong" reports. |
| 5 | Dialogue Doctor | AP (gap) | med (v2 default) | Clipped/noisy/off-mic dialogue lines found late; ADR is expensive. Gemini LISTENS to stems, ranks worst lines, drafts the ADR cue list. |
| 6 | Loudness Marshal | AQ (gap) | thin-must-have | Loudness compliance (EBU R128/ATSC A/85) is legally mandated per platform; violations bounce deliveries. ffmpeg math as metrics; agent diagnoses WHICH stem is hot; blocks delivery until fixed. Cheapest credibility in the whole build. |
| 7 | Cue Sheet Auditor | AR (gap) | thin-med | Music cue sheets drift out of sync with licenses; surfaces in legal or after air. Ledger matching + anomaly flags ("cue 7 used 12s past license"). Great detective beat for the video. |
| 8 | Conform Sentinel | AS (gap) | thin | Online conform can silently mismatch the locked cut. Hash + frame-count + reel-math verification. |
| 9 | Localization: Dub timing | C | med | Shows ship in 30–40 languages; AI dubbing fails weirdly (sync drift, truncated segments) and nobody watches the batch pipeline. Real Google TTS produces actual dubbed tracks; duration/sync measured against reference; severity-ranked fixes; Gemini listens to flagged samples. Demo ends with playable audio. |
| 10 | Localization: Caption specs | W | thin | Subtitle/caption files must meet broadcast specs (reading speed, line length, timing) or platforms reject them. Real parser validates output files; violations ranked; failing batches blocked before shipment. |
| 11 | Delivery & Compliance pack | AG | thin | Final-mile versioning chaos: wrong aspect ratios, missing cards, spec violations bounce after upload. ffprobe-vs-spec-sheet validation per destination; countdown-to-air-date telemetry; escalation for versions predicted to miss slots. |
| 12 | Trailer Bench | AT (gap) | v2 unless ahead | Trailers/promos have their own spec regime (runtime caps, rating cards, card counts). Gives catalog idea L a legitimate home. |
| 13 | Archive Keeper | AU (gap) | v2 | Libraries rot silently (bitrot, failing media). Checksum drift + storage telemetry — natural Grafana territory. |
| 14 | Accessibility Auditor | AV (v2) | v2 | Audio-description presence/placement, CC timing beyond format specs. |

Cross-cutting feature (not a station): **Consent/technique-only guard** — lives
inside Pickups and QC rollup; auditable ledger; InterPositive-derived rulebook.

---

## 6. The three views (sequencings), explained

### View 1 — Conventional chronology (industry order)
Post-production really proceeds roughly like this, and AO mirrors reality so the
demo teaches judges something true: turnovers (0) → ingest/dailies (1, overlaps
the shoot) → editorial lock + continuity (2) → VFX fixes/pickups (3) →
restoration runs as a parallel path for library content (4) → dialogue edit/ADR
+ mix (5) → music rights paperwork (6) → conform/mastering (7) → localization:
dub, subs, accessibility (8) → technical/editorial QC + compliance rollup (9)
→ versioning & delivery incl. trailers/socials (10) → archive (11). Our station
numbers above deliberately match these phase numbers.

### View 2 — Easy → hard build order (four waves)
Wave 1 **Deterministic** (days 3–5): pure code, zero GenAI risk, instant Grafana
graphs — delivery specs, loudness, caption parsing, conform checksums, file
arrival. Wave 2 **Measured** (days 5–8): classical signal/CV math needing
threshold tuning — sync detection, dub duration, diff-based continuity, dirt
stats, and the flicker/drift score. Wave 3 **Generative** (days 8–12): ascending
difficulty — background swap, then outpaint, then relight (stretch), plus
auto-retry and dialogue listen-classify. Wave 4 **Supervisor intelligence**
(days 12–14): cross-station correlation and morning reports — emerges last,
demos best. Rule: even though the generative wave is third, the Day-0 spike
(one background swap on 3 frames) happens BEFORE anything else, because it
carries the project's main visual risk.

### View 3 — Classes (capability taxonomy)
Six classes organize the same stations by what KIND of work they do:
**(A) Picture fixes** — Pickups, Restoration, visual continuity.
**(B) Audio fixes** — dub QC, Dialogue Doctor, loudness/mix.
**(C) Text & tracks** — caption specs, cue sheets, accessibility.
**(D) Choosing & arrangement** — triage/severity ranking, trailer assembly
rules, localization priority, version selection.
**(E) Pipeline hygiene** (discovered during this exercise) — ingest, conform
checksums, render health, archive, cost tracking.
**(F) Governance & compliance** (also discovered) — consent guard, delivery
specs, loudness law, platform QC packs.

---

## 7. How we DEMO each station (the 3-minute video plan)

Framing rule for the whole video: **fault-injection test bench, honestly
labeled.** "We built a miniature post house and broke it six ways; watch the
supervisor catch every one." One public-domain short film travels the entire
chain; ~25 seconds per station beat; before/after reel as the finale.

| Beat | On screen | Grafana MCP moment |
|---|---|---|
| Cold open | "I'm shipping a short film. Post has 10+ handoffs. Each silently bleeds days." Title card: POST COMMAND. | — |
| Ingest | Footage arrives; one card corrupt (we corrupted it). Alert fires; agent pulls Loki logs, names the broken offload. | alert→logs→annotation |
| Pickups pt.1 | Editor marks "flat sky"; background swap renders; flicker score spikes mid-render; agent investigates trace, retries with fixed anchors. | metrics+trace→auto-retry |
| Pickups pt.2 | "Need vertical for socials": outpaint reframe 16:9→9:16 plays side-by-side. Consent guard visibly BLOCKS a face-touching op (planted). | annotation + policy ledger |
| Dub | Spanish dub generated (real TTS); EP segment runs 800ms long; agent ranks severity, re-times. Play the audio. | metrics→incident→fix |
| Captions | Caption batch violates reading speed; blocked pre-shipment with reasons. | LogQL evidence |
| Delivery | Loudness check FAILS (-9 LUFS, legal limit -24); agent diagnoses hot dialogue stem via metric correlation. Fix lands; PASS. | cross-metric diagnosis |
| Finale | Project timeline UI: every event annotated; morning report compiles itself. Before/after reel. | dashboard links for humans |
| Meta close | Grafana AI Observability panel showing OUR agent's own tokens/latency/tool-calls during everything just shown. | self-observation |

---

## 8. Constraints, risks, techniques (carry-always)

**Proof tiers:** Tier 1 = real software doing real work, instrumented, failures
genuinely injected (our standard). Tier 2 = simulated device behavior, labeled.
Tier 3 = replayed data (avoid except clearly-labeled historical replay).

**Top risks:** (1) per-frame visual consistency/flicker on generative ops —
mitigated by short clips (2–5s), modest fps, anchored prompts, drift-score
monitoring, and demote-to-detect-and-flag fallback; (2) scope death by breadth —
mitigated by the FROZEN SCOPE below; (3) hosted-MCP interactive auth — mitigate
by running where browser auth completes once, or OSS server + service account.

**Recurring techniques worth keeping regardless of edits:** multimodal fusion
(Gemini watches content while Grafana watches systems); self-observing agent
(AI Observability on ourselves); write-path MCP usage (annotations/incidents,
not just queries); annotations-as-audit-trail framing.

---

## 9. FROZEN SCOPE PROPOSAL (awaiting owner sign-off)

**In scope (spine + 7 stations):** Spine; Ingest & Dailies (thin); Virtual
Pickups ★HERO (bg swap + outpaint; relight stretch); Localization Dub (med) +
Caption specs (thin); Delivery specs + Loudness Marshal (thin×2); Consent guard
(feature); Conform checksums (thin); Cue Sheet Auditor (thin, first cut if
slipping).

**v2 board (DO NOT TOUCH before submission):** Dialogue Doctor, Trailer Bench,
Archive Keeper, Accessibility, Restoration, Edit-Assist continuity, Handoff
Validator as visible UI (it still runs silently in the spine).

**Hard anti-creep rules:** station list frozen at design sign-off; never present
as a feature tour; unreliable hero ops demote rather than get cut; every station
ships through the same Grafana loop — nothing outside the observability fabric.

---

## 10. Status & immediate next steps

Done: idea convergence (51 ideas, 13 batches), full-catalog mapping to AO, gap
analysis (+7 stations), three sequencings, draft scope, demo arc design.
Pending owner decisions/actions, in recommended order:
1. Sign off (or edit) §9 frozen scope.
2. Run the **Day-0 spike**: one Gemini background-swap on 3 frames of
   public-domain footage; judge quality/flicker with our own eyes (~1 hour,
   cents in credits).
3. **Adversarial stress-test** of AO (theme fit, rules, tech risk, demo logic).
4. Write the formal **design doc** → `docs/specs/YYYY-MM-DD-post-command-design.md`
   per the brainstorming skill workflow, then implementation planning.

Timeline sketch (14 days): D0 spike+sign-off · D1–3 spine+Grafana wiring ·
D3–5 Wave 1 stations · D5–8 Wave 2 · D8–12 Wave 3 hero ops · D12–14 supervisor
intelligence + polish · D13–15 video + README + submit EARLY.

---

# AMENDMENTS — 2026-08-26 (post adversarial review + owner rulings)

These amendments SUPERSEDE any conflicting statement above (notably the
human-velocity timeline sketch and the "thin/demo" language wherever it could
imply faked functionality).

## A1. Owner Ruling 1: AO-FULL is LOCKED, built by coding agents

The adversarial review's timeline critique assumed human typing speed. Rejected:
**all implementation is done by coding agents**, working in parallel where
independent. Docs, scaffolding, tests, and boilerplate cost minutes, not days.
Consequence: the platform breadth is feasible; what does NOT change is the need
for **checkpoints**, because agent velocity ≠ agent correctness — verification
burden shifts to integration truth-checks against real media, not word-count
estimates.

### Priority stack (build in this order; deeper = richer product)

| Priority | Stations | Rationale |
|---|---|---|
| **P0 — product core** | Spine (job runner + OTel + Grafana MCP agent loop + timeline UI); Ingest & Dailies; Virtual Pickups ★HERO (bg swap + outpaint + relight-stretch); Loudness Marshal; Caption specs; Delivery specs | Minimum sellable product; every judging criterion covered |
| **P1 — depth** | Dub timing QC; Consent/technique-only guard ledger; Conform Sentinel | High-value differentiators, moderate cost |
| **P2 — richness until deadline** | Cue Sheet Auditor; Dialogue Doctor; Trailer Bench; Archive Keeper; Accessibility Auditor; Restoration; Edit-Assist continuity; Handoff Validator UI | Added strictly in listed order; each must pass its own integration check before the next starts |

### Checkpoint gates (truth-checks, not calendar promises)

- **G0 (before any build):** GenAI spike — real Gemini background-swap on 3 real
  frames; visual verdict recorded in this file.
- **G1:** End-to-end TRUTH CHECK — one real video file flows through spine +
  OTel + one thin station; agent performs one real Grafana MCP investigation;
  annotation appears in Grafana. No component mocked.
- **G2:** All P0 deterministic stations verified against real media artifacts.
- **G3:** Hero generative op passes quality gate on curated real footage
  (flicker score below threshold across ≥3 shots).
- **G4:** FULL JOURNEY — the real public-domain short traverses every completed
  station; supervisor compiles a real morning report; zero exceptions logged.
- **G5:** FREEZE — video recorded exclusively from the running product.

A failed gate demotes/cuts the lowest-priority unfinished work; it never
invites mocks.

## A2. Owner Ruling 2: THE INTEGRITY CHARTER (binding on all agents)

This is not a proof-of-concept and there is no such thing as "demo mode."
We are shipping a REAL product to a REAL buyer. Anything faked is deception,
and deception is penalized. Therefore:

1. **No simulated LLM calls.** Every model call in the running product is a real
   call to a permitted Google API, billed to real credits.
2. **No placeholder logic.** No stub functions, canned outputs, or "deterministic
   script for now, real version later." If a capability exists in the product,
   it works; if it doesn't work yet, it isn't in the product.
3. **No mock layers in the repository at all.** Dev conveniences like mock
   backends are banned outright — agents iterate against cheap real calls
   instead (Nano Banana ≈ $0.04/frame; TTS pennies; affordable).
4. **Synthetic INPUTS are allowed and labeled; faked FUNCTIONALITY is not.**
   There is no real client footage, so our test media is public-domain films
   and honestly-prepared fixture files (e.g., a deliberately corrupt card, an
   out-of-spec caption file). These are test DATA — standard engineering
   practice — provided the product processing them is fully genuine. Every
   fixture lives in `fixtures/` with a README stating what it is and why.
5. **Fault injection is announced, not hidden.** Where we break things to show
   resilience, the video narration says so plainly ("we corrupted this card").
   Honesty about test conditions is the opposite of deception.
6. **The recorded video shows exactly what a production user gets:** same code
   path, same auth, same latency, same failure modes. No editing tricks, no
   sped-up renders presented as real-time, no off-screen pre-computed results.
7. **Every claim in the README/video must be reproducible** from the repo by a
   stranger following the docs.

Violation protocol: any agent (or reviewer) discovering a violation flags it as
a CRITICAL finding; the offending component is either made real within one
working session or removed from the product surface entirely.

## A3. What stays true from the adversarial review

- Day-0/G0 spike remains mandatory first action (hero-op visual risk unchanged
  by build model).
- MCP auth plumbing (hosted OAuth vs OSS server + service-account token) is
  wired and PROVEN real by G1.
- Persona credibility: README will cite named industry sources for post-
  supervisor pain (turnover manifests, EBU R128 compliance, ADR costs).
- Breadth-vs-polish tension is resolved by the priority stack + gates: polish
  is enforced by G4/G5 truth-checks; richness extends downward from a working
  core, never ahead of one.
