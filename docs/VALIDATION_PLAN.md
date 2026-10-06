# Validation plan: what must be true before GamePlan calls are trusted

Written 2026-10-06, before any test below has been run. Bars are fixed here. Results go in `docs/validation_results_*.txt`; this file is not edited after a run except to add an amendment section with the date and reason.

## Why this exists

Gate 0 and Gate 0b showed the flags are internally consistent and stable. They did not show the approach is right or that it helps a hitter. Gaps: the model grades itself, there is no naive baseline, effect size is not in real terms, many cells were tested without correction, shrinkage was never tuned out of sample, and nothing has been tested at Single-A sample sizes or causally.

## Evidence levels (what each card element may claim)

| Level | Name | Meaning | What the card may say |
|---|---|---|---|
| L1 | Internal | Passes Gate 0 / 0b style tests (model-defined loss) | "Model flag" only |
| L2 | Raw outcome | Flagged pitches cost more in actual Statcast run value, independent of our model | "Costs him on pitches like this" |
| L3 | Beats baseline | Beats the naive coach rule on raw outcomes | "Better than the standard report" |
| L4 | Robust | Survives multiple-comparison correction, shrinkage sweep, two-way clustering, 3 of 4 seasons | Used as a default call |
| L5 | Causal | Pilot shows behavior or results change | Only level that may claim development benefit |

An element ships at the highest level it has earned and is labeled with it. Nothing claims L5 without a pilot.

## Season rule (applies to every test)

Run on 2022, 2023, 2024, 2025. Per-season grade, then a combined grade:

- **A**: bar met in 4 of 4 seasons.
- **B**: bar met in 3 of 4, no season significantly opposite.
- **C**: right sign in 3 of 4 but bar met in fewer than 3.
- **F**: wrong sign in 2 or more seasons, or any season significantly opposite on the primary metric.

Intervals: hitter-cluster bootstrap, 1,000 draws, fixed seeds, unless the test says otherwise.

## Tests

### V1. Raw-outcome validation (L2)
Question: do flagged pitches cost the hitter more in real results, with no model in the loss?

- Outcome: Statcast `delta_run_exp`, hitter perspective, per pitch (already in the day files).
- Comparison: flagged vs unflagged pitches from the same hitter-start, matched within location third x count x pitch family. Difference averaged across strata, weights by flagged count.
- Paths scored: L (starter-level), P (personal), E (excess), W (standing weak spots), on shapes S1 to S4.
- Secondary: whiff per swing, chase rate, xwOBA on contact.
- Bar: difference in the cost direction, interval excluding zero. Effect at least half the model-predicted lift (a model that is right but ten times too big fails calibration).
- Grade: season rule above.

### V2. Naive baselines (L3)
Question: does the model beat what a coach does without it?

Baselines, all built from earlier games only (no leakage):
- B1: his season-to-date worst pitch family x zone third by raw run value, ignoring the starter.
- B2: the starter's most-used non-fastball (the usage-only control, U).
- B3: the coach rule, B1 plus B2 combined: his worst zone and the starter's best pitch.

Metric: V1 raw-outcome lift per flagged pitch, plus coverage (flagged pitches per game).
- Bar: model path beats the best baseline on lift, difference interval above zero, and lift at least 25% larger in relative terms. Equal coverage within 1 pitch per game.
- If a baseline gets 80% or more of the lift, the model's extra complexity is not justified for that element and it is dropped from the card.

### V3. Effect size in real terms (reporting, not pass/fail)
- Runs per hitter per season = lift per flagged pitch x flagged pitches per game x games.
- Games needed to detect a change in one hitter's flagged-pitch chase or whiff rate at 80% power (simulation from his own variance).
- Classification: at least 1 run per hitter per season = "may be described as a performance edge"; below that = "recognition-training claim only, no win claim."

### V4. Multiple-comparison control
- Collect every p-value (bootstrap) from the pre-registered grid: shape x path x test x season.
- Benjamini-Hochberg at q = 0.05 over the full set.
- Grade per conclusion: A if it survives correction in 4 of 4 seasons, B in 3, C if it passes uncorrected only, F if it fails uncorrected.
- Report what fraction of earlier "PASS" lines survive. A drop below 60% is itself a finding and goes in the readout.

### V5. Shrinkage sweep, tuned out of sample
- K in {10, 20, 40, 80, 160} for the personal-path shrinkage.
- Choose K on 2022 and 2023 only; evaluate on 2024 and 2025 only. No peeking back.
- Bar: the sign and pass/fail of P and E vs L do not flip across the K grid, and the chosen K is within one grid step of 40. If the result depends on K, the personal paths are grade C at best.

### V6. Two-way clustering
- Bootstrap resampling hitters and starters jointly (cluster robust to both), plus week blocks for umpire and weather drift.
- Bar: V1 and V2 primary intervals still exclude zero. Intervals widening by more than 50% over the hitter-only bootstrap are reported.

### V7. Single-A sample-size curve
- Cap each hitter's history at 100, 150, 200, 300 prior pitches; cap starter history at 1, 2, 3 prior starts; compare to the full-history results.
- Metrics: B3 reliability (bar 0.40), V1 lift, coverage per game.
- Output: the smallest history at which the hitter-specific paths still pass. Below that, the card shows starter-level calls only.
- This is a stand-in until real California League data arrives; it does not replace it.

### V8. Pilot design stub (L5; needs org approval, not run now)
- Staggered start: hitters begin the clips at different weeks, so each is their own control.
- Primary outcome: chase and whiff rate on the flagged shape vs unflagged, pre vs post.
- Recognition measure: a short occlusion test on tablet before and after (to be specified with the org).
- Run the power calculation from V3 first. If the pilot cannot detect the minimum useful effect, say so before starting.

## Decision rules the results feed

1. If E or W beats L at V1 and V2 (grade B or better), calls are built from excess; otherwise L stays the call and weak spots show separately.
2. If a naive baseline matches the model at V2, that element is replaced by the baseline in plain language.
3. If V7 shows hitter-specific paths fail at Single-A history sizes, Visalia opens on starter-level calls plus the receipt only.
4. Ride and run traits (Gate 0b) stay card candidates; they need V1-style raw-outcome support before display.

## Run order and what each needs

| Step | Needs | Status |
|---|---|---|
| 2023 and 2022 data, Gate 0 and 0b | Downloads (running) | In progress |
| V1, V2, V3 | Existing rolling code plus `delta_run_exp` and baseline generators | Not written |
| V4 | All p-values from the above, all four seasons | After V1 and V2 |
| V5 | Rolling code with K as an argument | Small change |
| V6 | Bootstrap change | Small change |
| V7 | Rolling code with history caps | Small change |
| V8 | Org approval, Visalia data | Waiting |

## Final readout format

One table per season and a combined grade per test, then a plain-language paragraph: which card elements reached which level, what is dropped, and what the pilot must test.
