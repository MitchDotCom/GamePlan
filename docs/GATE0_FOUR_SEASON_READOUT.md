# Four-season readout (2022, 2023, 2024, 2025), written 2026-10-06

Rule from Gate 0 addendum 3: a result is **confirmed** if it passes in at least 3 of 4 seasons with no season significantly opposite. Everything below is public MLB data, starters only, rolling no-leakage. Result files are in `docs/` (`gate0_results_*`, `gate0b_results_*`, `validation_results_V1V3_*`).

## Bottom line

1. The signal is real but coarse. Flagged pitches cost the hitter more, and hitter patterns are stable. That holds in all four seasons.
2. The model's loss ranking does not beat a rule that just flags the starter's most-used pitches by height and side. On actual run value it fails that comparison in 64 of 64 cases.
3. The one shape where flagged pitches cost more in real results in all four seasons is **pitch family x height third x inside/middle/away (S2)**.
4. Two hitter-specific traits are confirmed: how he reacts to fastball ride and to breaking-ball run. Extension-adjusted velocity and the look-alike (tunneling) idea are rejected.
5. Nothing here is about recognition. These are decision-cost results, evidence level L1 to L2. Recognition needs the pre/post test.

## A. Gate 0 internal tests (model-defined loss)

| Test | S1 | S2 | S3 | S4 | Result |
|---|---|---|---|---|---|
| B1 lift, flagged vs other pitches (P path, range over 4 seasons) | 1.14 to 1.21 | 1.30 to 1.35 | 1.27 to 1.31 | 1.18 to 1.27 | Flagged pitches cost 14 to 35% more, every season. Confirmed |
| B2 personal beats starter-level (P minus L) | pass 4/4 | pass 3/4 (2022 interval touches 0) | pass 2/4, **opposite in 2022** | pass 2/4 | S1 and S2 confirmed. S3 and S4 not confirmed |
| B3 reliability (odd/even, corrected) | 0.52 to 0.57 | 0.46 to 0.50 | 0.42 to 0.45 | 0.43 to 0.48 | All pass, 16 of 16 |
| A coverage (median flagged pitches per game, bar 2) | 4 | 1 to 2 | 3 | 2 | S2 below the bar in 2025 and 2024 |
| C concentration (loss share vs pitch share) | fails | fails | fails | fails | 16 of 16 fail. Two calls hold about a third of his mistakes |

B2 is small even when it passes: +0.01 to +0.045 on the lift ratio.

## B. Raw-outcome validation (V1) and naive baselines (V2)

V1: do flagged pitches cost the hitter more in actual run value (Statcast `delta_run_exp`), net of the earlier-games league mean for the same kind of pitch? Bar: interval above zero.

| Shape and path | 2025 | 2024 | 2023 | 2022 | Seasons passing |
|---|---|---|---|---|---|
| S2 L (starter-level) | pass | pass | pass | pass | **4/4** |
| S2 P (personal) | pass | pass | pass | pass | **4/4** |
| S2 U (usage only, no model) | pass | pass | pass | pass | **4/4** |
| S1 P | no | pass | pass | no | 2/4 |
| S3 L | no | pass | pass | no | 2/4 |
| S3 P | no | pass | pass | no | 2/4 |
| S4 L and P | no | no | no | no | 0/4 |
| S2 E and W (excess paths) | pass | no | pass | no | 2/4 |

V2: model path minus the best naive baseline (his two costliest cells, his costliest cell plus the starter's top non-fastball cell, or usage only). Bar: interval above zero and at least 25% larger.

**Passing comparisons: 0 of 16 in 2025, 0 of 16 in 2024, 0 of 16 in 2023, 0 of 16 in 2022.** On S2 the usage-only control matches the model path (for example, 2025: U +0.63, L +0.64, P +0.60).

V3 effect size: about 0.5 to 1.7 runs per hitter over 150 starts on S2, and under 1 run on the other shapes. Detecting that in one hitter needs thousands of games. This supports a recognition-training claim only, not a win-edge claim.

## C. Post-hoc excess lift (model measure)

His excess loss on flagged pitches minus on others, runs per 100 pitches. Post-hoc, not pre-registered. Excess-ranked flags (E) and standing weak spots (W) beat starter-level flags (L) on every shape in every season where checked (2025, 2024, 2023, 2022). Example S2: E +0.36 to +0.41 against L +0.16 to +0.23.

This does not carry over to raw outcomes: E and W pass V1 on S2 in only 2 of 4 seasons and never beat the baselines. The gap is between the model's idea of "his weak spot" and what happens in actual results.

## D. Gate 0b traits

| Trait | 2025 | 2024 | 2023 | 2022 | Result |
|---|---|---|---|---|---|
| Fastball ride, hitter-specific slope (reliable and improves held-out prediction) | pass | pass | pass | pass | **Confirmed** |
| Breaking-ball run, hitter-specific slope | pass | pass | pass | pass | **Confirmed** (strongest: reliability 0.56 to 0.70) |
| Extension-adjusted velocity, all pitches | no | no (marginal pass without pitcher intercept) | no | no | **Rejected** |
| Extension-adjusted velocity, fastballs only | no | no | no | no | **Rejected** |
| Hitter-specific extension-adjusted velocity slope | no | no | no | no | **Rejected** |
| Pitch-type blindness (reliability bar 0.40) | pass | pass | no (0.34) | no (0.22) | Not confirmed (2 of 4) |

Look-alike (tunneling) path D: strong on the model measure (lift 1.4 to 1.6). The endpoint-matched direct test finds no whiff or chase effect in any of the four seasons. The first apparent effect was confounded by landing spot. **Rejected.**

## E. What this changes

- **Calls are not worth building around the model's loss ranking.** Build them from the starter's actual pitch mix on the S2 grid (family, height, side). Usage ranking is simpler and just as good on real results.
- **Keep two hitter-specific inputs:** his ride and run slopes. They are stable, improve held-out predictions, and match how coaches describe pitches (a sweeper with run, a fastball with ride).
- **Drop:** extension-adjusted velocity, look-alike weighting, pitch-type blindness as a hitter trait.
- **Wording:** the card says "decision cost" until the pre/post recognition test exists. It never says "recognition" or "mistake."
- **Recognition is the open question.** None of this measures it. See V8 and the assessment spec in `docs/VALIDATION_PLAN.md`.

## F. Not yet tested

- V4 multiple-comparison correction over the full grid. Several S2 passes above are in the "passes 2 of 4" band and are the ones most at risk.
- V5 shrinkage sweep, V6 two-way clustering, V7 Single-A sample-size curve, V9 hitter-specific referee.
- Everything here is MLB. Single-A hitter history is shorter and noisier, so hitter-specific results are likely weaker there.
- No causal test. Only the pilot can show that surfacing calls or clips changes behavior.
