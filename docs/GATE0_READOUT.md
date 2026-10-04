# Gate 0 readout (2026-10-04)

Pre-registered in `docs/GATE0_PREREGISTRATION.md` (committed 23:03 UTC, before any run). Code: `src/gameplan/recognition_paths.py`. Raw outputs: `docs/gate0_results_*.txt`. Every number below can be regenerated with:

```
python -m gameplan.recognition_paths --league data/league   --eval-start 2025-05-01 --split 2025-07-01 --out docs/gate0_results_2025_primary.txt
python -m gameplan.recognition_paths --league data/league24 --eval-start 2024-05-01 --split 2024-07-01 --out docs/gate0_results_2024_primary.txt
python -m gameplan.recognition_paths --league data/league --eval-start 2025-05-01 --split 2025-07-01 --min-hitter-pitches 150 --out docs/gate0_results_2025_hist150.txt
python -m gameplan.recognition_paths ... --extras    # the post-hoc controls
```

## What was tested, in baseball terms

For each hitter against each starter, May to September, 24,000+ hitter-starts per season: pick the two pitches the prep should focus on, using only earlier games, then see where his costly swing-or-take mistakes actually happened in that game. Three ways to pick:

- **P, personal:** the starter's pitches ranked by how often he throws them and how much this hitter has lost on them.
- **L, starter-level:** the same ranking with the league's losses, so every hitter gets the same two pitches against that starter.
- **D, look-alike:** the starter's non-fastball pitches, weighted toward the ones that start closest to his fastball path.

A "mistake" is a swing or take that the average-hitter model says was the worse choice, measured in runs. Four ways of defining a "pitch" were run: S1 pitch family by height in his zone; S2 adds inside/middle/away; S3 pitch type by height; S4 data-driven clusters by height.

## Results

| Question | 2025 | 2024 (confirmation) | Verdict |
|---|---|---|---|
| **Do the two pitches come up enough?** (median pitches per game; bar 2) | S1 4, S3 3, S4 2, S2 1 | same | Pass for S1, S3, S4. S2 too fine |
| **Are they real weak spots?** (loss per pitch vs his other pitches; bar 1.25 with CI above 1) | S3 1.28 (P), 1.27 (L); S4 1.27/1.25; S2 1.32/1.27; S1 1.18/1.16 | S3 1.27/1.26; S2 1.30/1.27; S4 1.21/1.21; S1 1.14/1.10 | Pass for S2, S3 both years. S1 fails for P and L. S4 holds in 2025 only |
| **Is it him or the starter?** (P minus L; bar: CI above 0) | S1 +0.021, S2 +0.045, S4 +0.019 pass; S3 +0.013 no | S1 +0.035, S2 +0.029 pass; S3 +0.009, S4 +0.002 no | Small. Real for S1 and S2 in both years only |
| **Does his pattern hold game to game?** (bar 0.40) | 0.43 to 0.57 | 0.42 to 0.52 | Pass, all definitions, both years |
| **Do two pitches carry most of the problem?** (bar: 30% of his loss and 1.5 times their share of his pitches) | Fail: S3 captures 35% of loss from 29% of pitches | Fail: same | Not supported. Mistakes are spread out |
| **Single-A-size history** (only 150 earlier pitches needed) | Same pattern; P minus L still passes for S1, S2, S4 | n/a | Holds |

## Controls added after seeing the primary results (labelled post-hoc, in `docs/gate0_results_*_extras.txt`)

- **Usage-only path** (just the starter's two most-used pitches): lift 0.95 to 1.08. So the loss-based ranking is doing real work.
- **Non-fastball path with no look-alike weight:** identical to D (lift 1.43 to 1.53, both years). The weight adds nothing; D's edge over P and L is only that secondary pitches cost hitters more than fastballs.
- **Look-alike test, pre-registered version:** passed in both years (whiff and chase). **Look-alike test matched on where the pitch ends up:** no effect in either year (chase gain +0.00003, CI includes zero in 2025; 2024 -0.00014). The pre-registered version was mixing up "looks like his fastball" with "ends up farther out of the zone".

## What this means for the plan

1. **Keep two focus pitches as a teaching focus, not as a fix.** They show up 2 to 4 times a game and the flagged pitches cost 25 to 50% more than his others. But they hold only about a third of his mistakes. Do not tell a coach the two calls cover most of the problem.
2. **Start with the starter-level ranking (L) and add the hitter as an adjustment.** The personal edge is small (lift +0.02 to +0.045) and shows in both years only for S1 and S2. L is close behind and needs no hitter history.
3. **Working definition: S3 (pitch type by height).** It is the only one that passes coverage, lift and reliability in both years, and it reads like coaching language ("sliders down"). S1 is the fallback when a hitter has little history, since it has the best personalization and reliability.
4. **Recognition target: the starter's breaking and offspeed pitches in the zones where hitters err.** The data supports that. It does not support the idea of ranking by "starts like his fastball". That idea stays a conjecture.
5. **Predictions on record versus what happened.** Coverage came in higher than I predicted (2 to 4, not 1 to 2). Personalization (B2) was supposed to fail and instead passed narrowly for two definitions. The look-alike test passed as pre-registered, then failed the stricter check.

## Limits

- The referee is a model of the average hitter, not truth. "Mistake" means worse than the average-hitter model's better option.
- MLB starters and hitters; the Triple-A and Florida State League run is pending (download in progress).
- Nothing here tests whether video training improves recognition or whether recognition is the problem. That needs clips and hitters.
- The look-alike measure reads early-flight position at 23.8 feet from a linear trajectory; a better measure (release point, spin, seams) could behave differently.
- The sample is MLB 2024 and 2025 with 24,000+ hitter-starts per season; a coach-sized claim for one hitter needs weeks of games.
