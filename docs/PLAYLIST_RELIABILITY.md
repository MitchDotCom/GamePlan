# Ride and run slope reliability, 2026-10-08

Pre-registered in `src/gameplan/playlist_reliability.py` (committed before the first run). Bar: Spearman-Brown corrected odd/even split-half r of at least 0.40, with the lower end of a hitter-bootstrap 95% interval above 0. Hitters: the first 70 batters found in 14 MLB games of 2025-06-08 to 06-10 (chosen by appearance, not by slope); history 2023 to 2025; at least 100 swings in the family in each half. Raw output: `playlist_reliability_2026-10-08.json`.

| Trait | Split-half r [95% CI] | Corrected | n hitters | Bar | Year over year (2024 vs 2025) r [95% CI] | n |
|---|---|---|---|---|---|---|
| Ride (fastballs) | 0.455 [0.196, 0.644] | 0.625 | 66 | met | 0.205 [-0.106, 0.521] | 55 |
| Run (breaking balls) | 0.598 [0.403, 0.752] | 0.748 | 56 | met | 0.458 [0.199, 0.670] | 45 |

Reading it:
- Both traits meet the pre-registered bar, so both stay in the hitter-specific playlists.
- Run is the stronger and more convincing of the two. It repeats across seasons too (0.46, interval above zero).
- Ride is thinner. The odd/even split mixes games from the same seasons, so it flatters stability. Year over year, ride is 0.21 and its interval includes zero. Ride lists should be shown with a thin-evidence tag until more hitters or seasons say otherwise.
- This is MLB only, from the simplified estimator, on 14 games' worth of hitters. Not a Single-A result.
