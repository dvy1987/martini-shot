# fixtures/pickups_frames — labeled synthetic INPUT frames (C-1.3)

Real JPEG frames generated with ffmpeg lavfi sources for the Pickups
Vision QC agent eval (A10-4). INPUT data only — they are what the agent
LOOKS at; they are not outputs of any station and never presented as
generated results (C-1.1/C-1.3).

Fixture design note: first-generation fixtures used SMPTE/testsrc test
patterns; the vision agent HONESTLY read their overlays and hard pattern
edges as render defects, so they were replaced with unambiguous smooth
gradient stills (clean class) vs genuinely damaged frames (defect class).

| file | label | intended role |
|---|---|---|
| stable_gradient.jpg | smooth blue gradient | clean extract |
| clean_field.jpg | smooth green gradient | clean extract |
| clean_dusk.jpg | smooth warm gradient | clean extract |
| noisy_gradient.jpg | heavy noise on gradient | degraded extract |
| corrupt_heavy_noise.jpg | extreme noise, low quality | corrupt-looking extract |
| artifacts_banding.jpg | noise + heavy compression | banding/artifact extract |

Generated 2026-09-06 via ffmpeg (`gradients` source + `noise` filter,
`-q:v` quality). Regenerate with the same commands if lost.
