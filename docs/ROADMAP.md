# GamePlan roadmap (v5, 2026-10-01)

## Where this stands

**Mission:** develop hitters first, win second. For a 9-man lineup against a specific starter, give a coach 2 to 3 viable approach options per hitter per count, log what the coach chooses, and review the game afterward. Hitters only, starters only. Public MLB data first, then TrackMan and Hawk-Eye. Personal project until the org approves.

### Built and working
| Piece | State |
|---|---|
| Prediction engine (swing vs take value by pitch shape, count, base-out, score, TTO) | Calibrated on MLB 2025. Scorecard 15 pass, 1 fail, 1 not measured |
| Hitter individualization | Passes on 2025 (+0.063, CI excludes 0) and on 2024 at a July 1 cutoff |
| Plan paths (Value, Contact-capped, experimental Hunt) | Contact-capped is a real alternative; Hunt is hidden because the model cannot value anticipation |
| Full-game viewer, two real games (HOU @ DET, BOS @ ARI) | Every plate appearance, both lineups, pitch-by-pitch review, pregame board, swing profiles, decision log. Checked against raw data. Browser test passes |
| Swing traits (bat speed, swing length, attack angle, tilt) | Descriptive only until a pre-registered test passes |
| TrackMan and Hawk-Eye onboarding kit | Infers column map, units and sign conventions from a sample export. Needs a real export to prove it |
| Public minor league feasibility | Triple-A and Florida State League evidence only. The California League is not public |

### Known gaps (be honest with coaches about these)
1. **The plan is silent on about half of pitches** (47% to 49% in both games). Evidence is thin or the options are too close. This is the single biggest credibility risk.
2. **Swing EV slope is 1.086**, outside the 0.95 to 1.05 rule. Replicated on 2024. Fix deferred.
3. **Not tested at Single-A.** No California League data, no TrackMan export yet.
4. **No coach has seen it.** Whether 2 to 3 paths are useful is a guess.
5. **Viewer craft (your feedback):** inconsistent capitalization, lowercase labels, pitch codes instead of names, uneven spacing, and the strike zone is a 15 pixel thumbnail beside a table instead of the centerpiece.
6. **Data is 2025.** The 2026 season is now complete and downloads from the same source (confirmed: one 2026 day returned 2,791 pitches).

## Phase 1: the coach prototype (now through Day 7)
Hard rule: no new model features. Only the viewer, the language and the dry run.

**1. Zone-first at-bat view (the main work).** The strike zone becomes the hero of the plate appearance screen.
- Large zone, batter's view, with the rulebook zone outlined, the hitter's own zone top and bottom, home plate and a handedness marker.
- Every pitch of the at-bat plotted in order as numbered dots, colored by result (take, swing and miss, foul, in play). The sequence reads left to right under the zone.
- The plan for the current pitch drawn on the zone itself (swing cells and take cells, no-call cells left clear). A stepper or scrubber moves pitch by pitch and the plan overlay changes with the count.
- Count, outs, bases, score and the pitch's type, velocity and location sit beside the zone. The old pitch table becomes a compact strip below.
- Pitch sequence replay: previous pitches stay faintly visible so the coach sees the pattern the starter used.

**2. Formatting and language pass.**
- Sentence case everywhere: "Strikeout", "Swinging strike", "Took", "Swung". Full pitch names ("Four-seam", "Changeup", "Slider") with the code in a tooltip.
- One type scale, one spacing scale, one color meaning per color. Results use the same words in the grid, the table and the zone.
- Consistent baseball vocabulary ("count", "chase", "zone swing") reviewed against what a hitting coach says.

**3. Say the limit on screen.** The no-call rate stays on the opening view with one plain sentence.

**4. Dry run (you, Day 4) and feedback capture.** You open the Arizona game cold and run the ten-minute script. Every place you hesitate gets fixed first. A one-page feedback sheet goes to the coaches (use, ignore, change, names they use).

**Gate to present:** browser test passes on both games, no unlabeled number on screen, you can run the walkthrough without me.

## Phase 2: use what the coaches say (weeks 2 to 6)
- Fold coach feedback in first. It outranks every item below.
- **Refresh to 2026 data.** Re-fit and re-validate on the full 2026 season as a third out-of-sample season. Keep 2024 and 2025 as the confirmation set.
- **Reduce silence.** Test whether the swing traits and a sequencing model raise the share of firm calls without hurting calibration. This is the highest-value modeling question.
- **Hitter traits predictive test** (pre-registered, 2025 plus 2024 or minor league confirmation; attack angle only from May 2025).
- **Sequencing and anticipation test.** Does a predictable-pitch premium exist? This decides whether "hunt" can ever be a real path.
- **Hitter decision profile across games** (what a hitter repeats, not one game).
- **Phase 0 decision on the swing slope.** Bring you the table with options. Nothing adopted without you seeing it.

## Phase 3: make it run on real club data (weeks 7 to 14)
- Real TrackMan sample export (you confirm what is allowed to be shared), then Hawk-Eye. Onboarding kit validated on it.
- Path generator with tags (Target, Aggression, Risk, Objective), 2 to 3 paths per count, ranked by evidence.
- Interactive laptop app: lineup in, board out, coach picks or overrides, decisions logged. Build on the viewer, not a rewrite.

## Phase 4: trial prep (weeks 15 to 26, Opening Day 2027)
- Org approval before any club data or staff use.
- Dry run on 2026 California League and spring data.
- Coach training, data tier setup, trial design measured on process metrics (coach use, decision quality), not a win claim.

## Decisions for you
| Decision | My recommendation |
|---|---|
| Relievers planned? | No, until after coach feedback |
| Refresh base data to 2026? | Yes, after the Day 7 presentation so it cannot destabilize the demo |
| Which coach first? | The hitting coach who will actually run pregame series meetings |
| Tuned whiff setting | Still not adopted; you see the table first |

## Risks
- Silence rate stays high after refresh (plan stays a decision aid, not a plan generator).
- Org approval delays Phase 3. Mitigation: everything through Phase 2 runs on public data.
- Zone redesign slips. Mitigation: ship the formatting pass first, it is independent.
