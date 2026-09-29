# GamePlan

Deterministic core for hitter-specific Go / No-Go plans and pitch-level scoring on three separate axes: decision, execution, result.

```
pip install -e '.[dev]' && pytest
```

## Layout

- `models.py`: hitter, pitcher, zone, rule, plan, pitch, evaluation. Feet / degrees / mph / ms.
- `plan.py`: `generate_grid_plan` turns a predicted-xwOBA surface into GO (baseline +.040) and NO_GO (baseline -.030) cells per pitch type.
- `evaluate.py`: `evaluate_pitch` returns decision score, execution score, quadrant, dev assignment, flags.
- `adjust.py`: `adjust_plan` extends fastball GO zones downward after a velocity drop.

## Where this deliberately departs from the blueprint

1. **Scoring is code, not the LLM.** The blueprint has Claude emit the scores as JSON. Same inputs must give the same score every time or the numbers can't be compared across games or coaches. Use the model for the post-event narrative and for drafting rules, not for arithmetic.
2. **Takes get no execution score.** The blueprint's example gives a take 100/100 execution. Nothing was executed, and it would inflate every disciplined hitter's execution average. `execution_score` is `None` on takes.
3. **Execution no longer adds degrees to milliseconds.** `Error_plane = |VAA diff| + |timing|` sums unlike units. Angle and timing now have separate penalties (`ANGLE_PENALTY`, `TIMING_PENALTY`). Both are guesses to calibrate against squared-up rate.
4. **Quadrant is decision x result only.** Execution is its own axis (rule 3 of the blueprint), so mixing it into Q1/Q4 breaks the separation. A good decision with bad execution and a bad result is Q2 with `MECHANICAL_CAGE_WORK`, not Q4.
5. **Velocity adjustment is one formula** (1 in per mph past a 2.5 mph drop, capped at 4 in). The blueprint's 2.5 mph -> 3 in and 3.0 mph -> 2.5 in contradict each other.
6. **Ordering when rules overlap:** priority, then NO_GO > CONDITIONAL > GO.
7. **Umpire misses** are detected from true location vs the call, score the decision normally, and suppress dev assignment.

## Things in the blueprint I would not build on

- "Decision point 175-220 ms" and the VAA plane-matching formula are simplifications. The swing is committed earlier than the pitch-recognition story implies, and the bat-plane/ball-plane relationship is a window, not a single target angle. `execution_score` uses `-pitch.vaa` as the target as a starting point only.
- Two different things are both called "VAA" (pitch approach angle vs swing attack angle). The code uses `Pitch.vaa` and `Swing.vaa_swing`.
- A predicted-xwOBA-by-location model per hitter per pitch type needs a lot of swings. At Single-A sample sizes most cells will be noise. Shrink toward league or level priors before trusting a NO_GO on a specific hitter.
- One-pitch dev assignments are noisy. Aggregate `dev` over a window before acting on it.
- Not modelled yet: pitch tunneling, catcher framing, sequencing, storage (PostgreSQL), video sync.

## Tunable constants

`evaluate.py`: decision scores, `GOOD_DECISION`, `ANGLE_PENALTY`, `TIMING_PENALTY`, `GOOD_EXECUTION`, `PROTECT_TOLERANCE_FT`. `SCORE_CONDITIONAL_NEUTRAL` is a placeholder: a non-protect CONDITIONAL rule has no defined right answer yet.

## Savant (`savant.py`)

- `build_url(batter_id, season, pitch_types)` + `fetch_csv(url)`: pitch-level Statcast search CSV. Needs `baseballsavant.mlb.com` allowed in the environment's network policy; without it, download the CSV by hand and pass the text in.
- `parse_swings(csv_text)`: swing rows only. Value per swing is xwOBA on balls in play, 0 on whiffs and fouls. IVB is `pfx_z * 12` (proxy); VAA is computed from `vy0, vz0, ay, az`.
- `fit_hitter_model(csv_text, batter_id, k=30)`: per-cell xwOBA shrunk toward the league mean for that pitch type and cell. The league prior is only as good as the CSV you pass, so include many hitters. Use `model.hitter_baseline` as `Hitter.baseline_xwoba` so the GO/NO_GO margins compare like with like.
- Caveat: baseline here is value per swing (whiffs count as 0), not batted-ball xwOBA. `evaluate._result_good` compares batted-ball xwOBA to `baseline_xwoba`, so with a swing-based baseline it will be too strict. Split these into two fields before using real data.
