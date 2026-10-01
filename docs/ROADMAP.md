# GamePlan roadmap (v6, 2026-10-01): ship daily

Mission: develop hitters first, win second. For a 9-man lineup against a specific starter, show where each hitter can do damage, where he should swing or take, and review what he actually did. Hitters only, starters only. Public MLB data first, then TrackMan and Hawk-Eye. Personal project until the org approves.

## State today (end of Day 4)

| Shipped | Notes |
|---|---|
| Two full games, both lineups, every plate appearance | HOU @ DET 2025-08-19 and BOS @ ARI 2025-09-06. Checked against raw data. Browser test passes |
| Zone-first at-bat view | Large zone, hitter's own strike zone outline, numbered pitches by result, plan overlay per pitch, stepper |
| Skip control | Bunts, intentional walks, catcher interference, automatic calls and position players pitching are skipped automatically. Coach can skip or restore any at-bat. Skipped at-bats leave the totals. Logged and exported |
| Pregame board | Value and Contact-capped plans per count, same zone |
| Hosted private pages | Both games, republished with each change |

Known limits, said out loud to coaches: the plan is silent on about half of pitches; one calibration check fails (swing value slope 1.086); nothing tested at Single-A yet.

## The next question: can he damage what he swings at?

This is the main build now. Three layers, in the order they ship.

1. **What he did on the swing.** Per swing: bat speed, swing length, attack angle, swing path tilt, exit velocity, launch angle, xwOBA, squared up. Shown against his own norm and the league's, beside the pitch.
2. **Plane fit.** Angle between his bat path and the pitch's path (attack angle plus the pitch's approach angle). Only labeled good or poor if the league data says the angle carries signal. The test is running (`plane_match.py`, results in `docs/plane_match.txt`). If it shows nothing, the label does not ship and I tell you.
3. **Damage versus the starter's arsenal.** For each pitch type the starter throws: how often, how hard, where, and what this hitter's history says about contact quality and whiffs on it, shrunk toward the league so small samples do not mislead. Then the game view asks the real question: of his swings, how many were at pitches he can damage versus pitches that are weak spots for him, and how many chases were on weak spots.

Hard limit to respect: a typical hitter has well under one of his own swings behind any single zone cell. So the arsenal table is by pitch type and zone group, not by cell, and every number carries its sample size.

## Situation register (nuances that change what an at-bat means)

| Situation | Handling |
|---|---|
| Bunt or sacrifice | Skipped automatically; coach can restore |
| Intentional walk | Skipped automatically |
| Pitchout | The pitch is left out of scoring; the rest of the at-bat counts |
| Catcher interference, automatic ball or strike | Skipped automatically |
| Position player pitching | Skipped automatically (average pitch speed under 70 mph) |
| Runner on third, fewer than 2 outs | Switchable contact-first policy (shipped) |
| Hit-and-run, called play, hitter told to take | Not visible in public data. Coach skips it by hand with a reason (shipped) |
| Extra innings automatic runner | Base state is already in the plan |
| Blowout or garbage time | Next: leverage flag, off by default, needs coach input on the cutoff |
| Two-strike approach, protecting | Already in the plan; "choke up and shorten up" shows in bat tracking, so layer 1 will show it |
| Pinch hitter, platoon changes | Next: flag at-bats where the hitter entered cold |

## Schedule

| Day | Ships | Gate |
|---|---|---|
| D4 (done) | Zone-first view, skip control, republished pages | Browser test on both games |
| D4-D5 (done) | Traits test run: personal sweet band passes for whiffs (2025 and 2024); bat speed, swing length, path deviation alone and every damage test do not. Layers 1 to 3 built (per-swing bat tracking, personal band, damage versus arsenal) | docs/traits_test.txt |
| D5 | Layer 1 (per-swing bat tracking card) and layer 3 (hitter versus arsenal table, swings at damage pitches versus weak spots). Both games rebuilt. Plane-fit decision from the league table | Numbers spot-checked against raw rows; browser test |
| D6 | Layer 2 if the data supports it. One-page pregame sheet per hitter (arsenal, damage table, zone plan) for the series meeting. Your dry run | You can run the walkthrough alone |
| D7 | Present to hitting coaches. Feedback sheet | |
| Week 2 | Coach feedback first. Refresh to 2026 data. Pre-registered test of whether bat-tracking traits improve predictions (decides whether they enter the plan or stay descriptive) | Test passes or traits stay descriptive |
| Week 3 | Sequencing and anticipation test (can "hunt a pitch" ever be a real path). Decision profile across games. Leverage and pinch-hitter flags | |
| Weeks 4-6 | Decide the swing-slope fix (you see the table). Reduce plan silence with traits and sequencing if they pass | |
| Weeks 7-14 | Real TrackMan then Hawk-Eye export through the onboarding kit. Path generator. Interactive laptop app | Needs a sample export and org sign-off |
| Weeks 15-26 | Org approval, dry run on spring data, coach training, trial setup for Opening Day 2027 | |

## Decisions for you
| Decision | My call |
|---|---|
| Relievers planned? | No, until coach feedback |
| Refresh to 2026 data? | Yes, in week 2, not before the D7 presentation |
| Blowout cutoff for skipping | Ask the hitting coach what margin and inning they would call garbage time |
| Plane-fit label | Ships only if the league table shows a real pattern |

## Risks
- Hitter-specific damage is thin at small samples. Mitigation: pitch-type groups, shrinkage, visible sample sizes.
- Plan stays silent on about half of pitches. Mitigation: say it on screen; test whether traits and sequencing reduce it.
- Org approval delays real data. Mitigation: everything through week 6 runs on public data.
