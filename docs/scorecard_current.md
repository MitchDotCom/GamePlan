| # | Criterion | Rule | Result | Status |
|---|---|---|---|---|
| 1 | wOBA scale in code equals FanGraphs 2025 | in [1.257, 1.257] | 1.257 | PASS |
| 1 | count run values vs published (0-0 strike, 0-1 ball, 1-1 strike): max relative error | <= 0.15 | 0.1013 | PASS |
| 1 | league-wide wOBA (published weights, proper denominator) vs FanGraphs .314 | <= 0.004 | 0.001743 | PASS |
| 1 | league-wide wOBA increase TTO1 to TTO2 vs starters, points | in [5.0, 16.0] | 6.932 | PASS |
| 1 | league mean four-seam IVB, inches | in [14.0, 18.0] | 15.82 | PASS |
| 1 | league mean curveball IVB, inches | in [-12.0, -8.0] | -10.25 | PASS |
| 2 | swing EV calibration slope | in [0.95, 1.05] | 1.086 | FAIL |
| 2 | take EV calibration slope | in [0.95, 1.05] | 0.9915 | PASS |
| 2 | largest decile gap, realized minus predicted (wOBA points) | |x| <= 0.02 | 0.01267 | PASS |
| 2 | largest segment gap (count, family, side, TTO) with CI excluding 0 | |x| <= 0.02 | 0.016 | PASS |
| 3 | year-over-year whiff Brier skill vs league, CI lower bound | >= 0.0 | 0.02204 | PASS |
| 3 | year-over-year xwOBAcon MSE skill vs league, CI lower bound | >= 0.0 | 0.0023 | PASS |
| 4 | hitter-vs-league disagreement: swing-take gap difference, CI lower bound | >= 0.0 | 0.02266 | PASS |
| 4 | S lost when count awareness is removed, CI upper bound | <= 0.0 | -0.0005484 | PASS |
| 5 | hitters recognize pitch type before the decision point (needs pilot data) | >= 1.0 | - | NOT MEASURED |
| 6 | pilot minimum detectable difference, runs per pitch, must be <= expected effect | <= 0.02 | 0.0166 | PASS |
| 7 | confident GO pitches separate swing from take better than thin-support GO pitches: CI lower bound of the gap difference (runs) | >= 0.0 | 0.04063 | PASS |

FAIL: 1  NOT MEASURED: 1  PASS: 15
