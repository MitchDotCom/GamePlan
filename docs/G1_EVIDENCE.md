# Decision gate G1: evidence (2025 MLB, public Savant data; fit before 2025-07-01)

> **Correction 2026-10-04.** Section 3 (and point 5 under "What this says") compared MLB with a file that was labelled minor-league but was MLB data (the `bulk --minors` download returned MLB games). Those minor-league sample-size findings are invalid. The California League is still not in public Statcast, and no real Triple-A or Florida State League sample has been checked.


Raw output: `relevance_ablation.txt`, `relevance_paths.txt`, `feasibility_current.txt`. Nothing here is adopted automatically.

## 1. Which inputs change calls (138,076 held-out starter pitches)
Default calls: GO 25.9%, NO_GO 42.5%, no call 31.6%. No variant ever flipped a call (GO to NO_GO); variants only add or drop calls.

| Input removed or changed | Called pitches changed | S change (runs) | Reading |
|---|---|---|---|
| Count awareness (score every pitch as 0-0) | 26.6% | -0.018 [-0.027, -0.009] | Matters |
| Confidence bounds (point estimate only) | 31.7% added | -0.033 [-0.039, -0.028] | Matters |
| Pitch shape (type only / type+velo / location only) | 4.6% / 4.9% / 2.1% | -0.007 / -0.005 / -0.022 | Shape matters; location-only is worst |
| Hitter-specific term (league model) | 7.6% | -0.002 [-0.006, +0.002] | Few calls change; effect not distinguishable from zero |
| Count as a model feature | 2.8% | -0.0002 | No effect on separation (calibration slope worse, see slope_diag) |
| Time-through-order effect | 1.3% | -0.001 | Negligible |
| Base-out weights (mild / strong) | 0.7% / 1.4% | +0.000 | Negligible overall |
| 3-ball zone surface | 0.1% | -0.0004 | Negligible |
| Call threshold 0.01 / 0.04 | 0% / 0.8% | 0 / +0.001 | Confidence bounds, not the threshold, decide |

## 2. Do the three styles differ? (25 real starter games, 138 hitter matchups per count)
| Count | CONTACT differs from VALUE (median share of pitches) | Value gap CONTACT (runs/100) | HUNT differs | Value gap HUNT (runs/100) |
|---|---|---|---|---|
| 0-0 | 17% | +0.15 | 65% | -1.12 |
| 1-0 | 20% | +0.25 | 53% | -0.73 |
| 0-1 | 15% | -0.04 | 70% | -2.12 |
| 1-1 | 12% | 0.00 | 55% | -1.88 |
| 2-1 | 17% | +0.11 | 52% | -1.14 |
| 3-1 | 0% (no swing cells) | 0 | 0% | 0 |
| 1-2 | 11% | -0.06 | 0% (reverts at two strikes) | 0 |

CONTACT is a genuine near-equal alternative (different calls on 12-20% of pitches, value within about 0.25 runs per 100). HUNT as built is clearly worse (-0.7 to -2.1 runs per 100). The model has no term for the benefit of sitting on a pitch (anticipation), so it cannot value hunting at all. At 3-1 and two strikes there is effectively one path.

## 3. Sample sizes (MLB 2025 vs public Triple-A + Florida State League 2025)
- Hitters with 300+ tracked swings: 386 (MLB) and 374 (MiLB); median 380 and 359. Starters: median 6 starts both.
- Full pitch shape on 100% of pitches; bat tracking on 97.5% / 97.6% of swings; Savant xwOBA on 100% of balls in play.
- Plan cells: GO 20%, NO_GO 41%, no call 39% (thin evidence 26%) in both. Effective number of the hitter's own swings behind a cell: median 0.2.

## What this says
1. Plans are driven by the league surface by pitch shape and count. The hitter's own per-cell data adds almost nothing at these sample sizes, anywhere. Per-cell hitter heat maps are mostly the league map.
2. The inputs that change calls are count, confidence bounds and pitch shape. Time through the order, base-out, 3-ball zone and the count feature change under 3% of calls.
3. Hitter individualization has to come from low-dimensional hitter traits (whiff skill, contact quality, swing path and bat tracking relationships) rather than per-cell heat maps.
4. "Hunt" needs its own valuation (an anticipation effect), which needs a sequencing model and a test of whether hitters do better on predictable pitches.
5. Public minor league data (Triple-A and Florida State League) looks like MLB in size. California League is not in it.
