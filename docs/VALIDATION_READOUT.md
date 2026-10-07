# Validation readout, V1 to V9 (2022 to 2025), written 2026-10-07

Plan and bars: `docs/VALIDATION_PLAN.md` (amendments 1 to 3). Rule for "confirmed": passes in at least 3 of 4 seasons with no season significantly opposite. Everything is public MLB data, starters only. Result files are named in each row.

## Grades

| Test | Question | Grade and result | File |
|---|---|---|---|
| V1 | Do flagged pitches cost more in real run value? | **A on S2** for L, P and U (4 of 4 seasons). Not confirmed on S1, S3, S4 | `validation_results_V1V3_<year>.txt` |
| V2 | Does the model beat a simple rule? | **F.** 0 of 64 comparisons pass | same |
| V3 | How big is it? | About 0.5 to 1.7 runs per hitter per 150 starts. Recognition-training claim only | same |
| V4 | Does it survive correction for many tests? | **A** for V1 S2 (L, P, U and both baselines) and B2 on S1. 48 of 53 passes survive (91%) | `validation_results_V4.txt` |
| V5 | Does it depend on the shrinkage setting? | **C** for the personal path. S2 passes at every K (20 of 20), but the K chosen on 2022-23 (160) did not carry to 2024-25 and sits two grid steps from 40 | `validation_results_V5_readout.txt` |
| V6 | Do wider (hitter and starter) intervals still pass? | **A** for P and U on S2 (4 of 4), **B** for L (3 of 4). E 1 of 4, W 2 of 4 | `validation_results_v6_<year>.txt` |
| V7 | Does it hold with earlier-game cutoffs? | S2 passes for P in every setting in every season (24 of 24). Built as a "calls start here" cutoff, not true history size | `validation_results_v7_<year>.txt` |
| V7b | Does it hold at exact history sizes? | S2: P passes 4 of 4 at 500+ pitches, 3 of 4 at 300 to 499, 2 of 4 at 200 to 299, 3 of 4 at 100 to 199 (one season significantly negative for P minus L). Smallest bin confirmed for P: **300 to 499 pitches** | `validation_results_v7b_<year>.txt` |
| V8 | Does it train recognition? | Not run. Needs org approval. Spec in the plan | n/a |
| V9 | Is the finding an artifact of grading everyone as average? | **A** for L, P and U on S2 (4 of 4). Correction is small (loss correlation 0.993) | `validation_results_v9_<year>.txt` |

## What is solid

1. **On the S2 grid (pitch family x height third x inside/middle/away), flagged pitches cost the hitter more in real results.** Four seasons, real run values, wider two-way intervals, correction for many tests, a hitter-specific referee, and any shrinkage setting. This is the strongest finding in the project.
2. **The personal path is stable on S2** but not better than the simple paths anywhere. Personal minus starter-level is never significantly positive in V7b, and passes in 1 of 100 cells in V5.
3. **A simple rule matches the model on real results.** Flagging the starter's most-used pitches by family, height and side (path U) is as good as anything else we built.

## What is not solid

1. **S1, S3 and S4 do not hold up in real results.** They pass in 2 of 4 seasons at best.
2. **E and W (his weak spots) are the weakest.** They look best on the model's own measure and worst on real results.
3. **History size.** Below about 300 earlier pitches the personal path is not confirmed, and the starter-level and usage-only paths also pass less often. At 100 to 200 pitches nothing is reliably confirmed. This matters for Single-A. It is MLB data cut down, not Single-A data.
4. **V9 is a mild correction.** A two-number shift per hitter, shrunk hard toward the league, so it cannot show the finding is safe against a full hitter-specific model.
5. **V4 uses a normal approximation** to the bootstrap intervals.

## What this means for the product

- Build the card's flagged pitches from the starter's actual pitch mix on the S2 grid. The referee ranking adds no value on real results.
- Do not promise personalization from public-data history alone. Show his own history as context, and label it by sample size.
- At Single-A before about 300 earlier pitches, use starter-level flags and say so.
- Keep the claim to recognition training. The effect is under about 2 runs per hitter over 150 starts, and nothing here measures recognition.
- Ride and run slopes (Gate 0b) remain the hitter-specific inputs with evidence.

## Still open

- V8, the recognition measurement and pilot. This is the only test that can show training works.
- Real Single-A (California League) data. Everything above is MLB.
- A full hitter-specific referee refit (stronger than V9).
