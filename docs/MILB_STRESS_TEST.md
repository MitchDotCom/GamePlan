# Triple-A and Florida State League stress test, 2026-10-08

Data: Savant's public game feed for 2025 regular-season games, found through the Stats API schedule (`gameplan.milb_feed`). Verified: full pitch tracking for Triple-A (sportId 11) and Florida State League (sportId 14, leagueId 123) games; none for the Carolina and California League games checked; no clips for any minor-league game (0 of 32 links). The minor-league CSV search was not used (see `milb_feed.py` docstring). Code: `milb_study.py`. Same estimator and same bar as the MLB test: corrected split-half r at least 0.40 with the lower end of a hitter-bootstrap 95% interval above 0.

## Florida State League, 2025 (710 final games)

| | |
|---|---|
| Pitches in the feeds | 199,923; 178,857 tracked (89.5%); 70 games had no tracking at all |
| Hitters with at least 300 tracked rows | 192 |

Coverage: how many hitters have the 150 swings the code needs before it reports a slope.

| Trait | Full season: hitters with 150+ swings (median swings) | By 2025-06-15 |
|---|---|---|
| Ride (fastballs) | 122 of 192, 63.5% (197) | 73 of 192, 38.0% (113) |
| Run (breaking balls) | 29 of 192, 15.1% (81) | 0 of 192 (46) |

Reliability (odd/even games, at least 100 swings in each half):

| Trait | Hitters | r [95% CI] | Corrected | Bar |
|---|---|---|---|---|
| Ride | 87 | 0.26 [-0.01, 0.49] | 0.41 | not met (interval includes 0) |
| Run | 12 | not interpretable (12 hitters; r = -0.62) | n/a | cannot assess |

## Is that the level or the amount of data? MLB, 2025 only (79 hitters)

The earlier MLB test used three seasons. On 2025 alone:
- Coverage: ride 95% of hitters, run 76% (median 486 and 252 swings).
- Reliability: ride 0.24 [-0.04, 0.47], corrected 0.39, bar not met. Run 0.49 [0.24, 0.69], corrected 0.66, bar met (51 hitters).

Caveat: the MLB hitters here are mostly regulars with full seasons; the Florida State League set includes anyone with 300 tracked rows, so part-season hitters and promotions are in it.

## What this says
1. Ride's weakness is mostly a data-volume problem, not a level problem. With one season it fails the bar in MLB too (0.39) and in the Florida State League (0.41, interval includes 0). It cleared the bar only with three seasons of history. So ride lists should always carry the thin tag, and at Single-A they are weaker still.
2. Run cannot run at Single-A on one season. Only 15% of hitters reach 150 swings at breaking balls by season end, none by mid-June, and too few hitters have 100 per half to test its reliability. In MLB one season is enough for run; Single-A hitters see fewer pitches and the tracked share is lower.
3. Therefore early in a Single-A season, hitter-specific lists will mostly not exist, and the starter's usage list (validated, no hitter history needed) is what the tool shows. This is the intended fall-back, and it is the V7 finding (history of 100 to 299 pitches is weak) showing up with real minor-league data.
4. Multiple seasons of the same hitter, carried across levels, are what would make ride and run usable. That needs a stable player ID across levels and the org's own history (the earlier CSV and ID discussion).

## Not done yet
- Triple-A: fetch is running; results will be added here.
- Year-over-year at these levels (needs the 2024 season fetched).
- The lineup command from these feeds for a real Single-A starter.
