# Pilot design (draft, to run only after MLB validation and MiLB loader are done)

## What the pilot has to answer

Not "does the model predict well" (MLB validation does that) but: when hitters are given the plan, do their swing decisions change in the intended direction, and does decision quality improve, without hurting them?

## Why outcomes alone cannot answer it

Per-pitch run value has an SD of about 0.33 runs on swings and 0.08 on takes (2025, 340k pitches). The value of following the plan is small per pitch: hitters already follow the call about 70% of the time, and swinging beats taking by about 0.07 runs on GO pitches, so full compliance is worth roughly 0.02 runs per GO pitch at most, and less after selection bias. Minimum detectable differences at 80% power and 5% two-sided (`python -m gameplan.pilot`):

| pitches per arm | mixed pitches (SD 0.21) | swings only (SD 0.33) |
|---|---|---|
| 250 | 0.053 runs | 0.083 |
| 600 | 0.034 | 0.053 |
| 2,500 | 0.017 | 0.026 |
| 10,000 | 0.008 | 0.013 |
| 25,000 | 0.005 | 0.008 |

A single hitter over a season (about 2,500 pitches) can only show effects of about 0.017 runs per pitch. A stepped rollout of 12 hitters, 8 periods, 400 swings per period has 14% power to detect a 0.005-run effect. So: results (wOBA, runs) are reported but are not the pass/fail measure.

## Design

- **Unit:** hitter-period (one hitter, one week or one 10-game block).
- **Arm structure (recommended):** stepped rollout. Every hitter starts on control (no plan shown), then switches to the plan at a staggered date, and stays on it. Each hitter is his own control; the staggered start separates the plan from time trends (weather, pitcher quality, season fatigue). Alternative for fewer hitters: alternating on/off blocks per hitter, at the cost of carryover (a hitter who has seen a plan does not forget it).
- **Analysis:** hitter and period fixed effects, treatment indicator, intention-to-treat (a hitter counts as treated whether or not he followed the plan). Standard errors clustered by hitter and by opposing starter (two-way). Report the effect with its interval, not just a significance flag.
- **Compliance is measured, not assumed:** share of strong-call pitches where the action matched the call. A plan nobody follows tests nothing.

## Measures (pre-registered; changing them after seeing data invalidates the pilot)

Primary (process): decision value per 100 pitches, model-based. Expected runs of the action taken minus the alternative, from the plan snapshot in force at each pitch.

Secondary (process): chase rate (swings at pitches almost certain to be called balls), zone-swing rate (swings at pitches almost certain to be strikes), compliance rate, squared-up rate where bat tracking exists.

Guardrails (must not worsen beyond a stated margin): strikeout rate, walk rate, hard-hit rate.

Reported, not decisive: wOBA, xwOBA, run value.

Before a metric is used it must pass a reliability check: hitters must differ from each other consistently across alternate halves of the season (`python -m gameplan.pilot`, split-half over alternate games; results in `docs/pilot_reliability.txt`). A metric with near-zero reliability cannot show a hitter-level change.

## What must be true before starting

1. MLB validation scorecard (`docs/scorecard.md`) has no FAIL in measures 1 to 4, and measure 7 (confidence coverage) is built and passes.
2. MiLB loader exists and per-system offsets between TrackMan and Hawk-Eye are estimated, or the pilot is restricted to parks with one system.
3. Each pilot hitter has enough tracked swings for a hitter-specific plan (about 200 or more, per the learning curve) or the plan is explicitly league-plus-coach-report; coach report trust weights are set from the ledger.
4. Confidence and sample size are shown on the coach card so cells with thin support are not presented as calls.

## Player development and ethics

Participation is opt-in. The plan is decision support, never a compliance score used in evaluation or promotion decisions. Hitters in DEVELOP mode keep their own zone; the pilot reports separately for COMPETE and DEVELOP. Any hitter or coach can turn the plan off at any time and that is recorded, not penalized.

## Stopping rules

Stop and review if guardrails worsen by more than the pre-set margin for two consecutive periods, or if compliance is under 30% after four weeks (the plan is not usable as delivered, so results would not be interpretable).
