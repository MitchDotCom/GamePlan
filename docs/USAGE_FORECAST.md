# Do recent starts predict the next start's shape mix? 2026-10-08

Pre-registered in `src/gameplan/usage_forecast.py` before the first run (committed first). Test period: starts on or after 2025-07-01; the choice among configurations was made on starts before that date; predictors use only earlier games. A start is a pitcher-game with at least 45 tracked pitches and at least 3 earlier starts. Metric: coverage@3, the share of a start's pitches to a batter side that fall in the predicted top 3 (family x nine-pocket) shapes. Averages are per pitcher, then across pitchers; intervals bootstrap pitchers. Bar: selected configuration beats the league default by at least 0.05 with the interval's lower end above 0.

| | MLB 2025 | Florida State League 2025 |
|---|---|---|
| Pitchers, starts | 416, 5,196 | 249, 1,481 |
| League default top 3 (coverage) | 0.266 | 0.271 |
| Oracle (the start's own top 3, upper bound) | 0.444 | 0.446 |
| Selected configuration (lowest training log-loss) | all earlier starts, half-life 4 | all earlier starts, half-life 4 |
| Selected coverage, lift vs league [95% CI] | 0.333, +0.067 [+0.058, +0.077] | 0.325, +0.055 [+0.037, +0.073] |
| Bar met | yes | yes |
| Current default (last 4 starts, half-life 2): coverage, lift [CI] | 0.325, +0.059 [+0.050, +0.068] | 0.318, +0.047 [+0.030, +0.066] |

Test coverage by number of starts pooled (half-life 4):

| Starts pooled | 1 | 2 | 3 | 5 | 8 | all |
|---|---|---|---|---|---|---|
| MLB | 0.290 | 0.314 | 0.321 | 0.328 | 0.331 | 0.333 |
| Florida State League | 0.272 | 0.301 | 0.316 | 0.320 | 0.324 | 0.325 |

## Reading it
- Yes, recent starts predict the next start. The pooled mix beats the league default by 5 to 7 points of coverage in both leagues, and the interval excludes zero.
- It closes about 38% (MLB) and 31% (Florida State League) of the gap between the league default and the oracle. Most of the start-to-start variation (game plan, opponent, feel) is not predictable from history.
- One start alone is no better than the league default in the Florida State League (0.272 vs 0.271) and only a little better in MLB. Gains come from pooling: most of it by 3 to 5 starts, a little more after.
- Recency weighting barely matters: half-lives 2 and 4 and equal weights are within 0.005 of each other. Half-life 1 (heavy recency) is worse.
- The default (4 starts, half-life 2) trails the selected configuration by 0.007 to 0.008, below the 0.01 threshold set beforehand, so by the rule it stays. The curve is flat past 5 starts. Reasonable to pool up to 8 when available.
- Same shape at both levels, so it is not an MLB-only effect. Triple-A pending.

## Limits
- This tests the starter's mix, not whether showing those pitches trains recognition.
- "Start" is a 45-pitch proxy. Opener games, injuries and role changes are not handled.
- Pitchers with fewer than 3 earlier starts are excluded; a Single-A starter early in the year may have none, so the league default is what is left.
