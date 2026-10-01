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
- `parse_swings(csv_text)`: swing rows only. Fouls are kept as contact with no batted-ball value; xwOBA is set on balls in play only. IVB is `pfx_z * 12` (proxy); VAA is computed from `vy0, vz0, ay, az`.
- **Whiff-adjusted contact quality (CQ)** = (1 - whiff rate) * mean xwOBA on balls in play. `ContactQualityModel` / `fit_hitter_model(csv_text, batter_id)` shrinks the whiff rate (`k_swing`, default 30) and xwOBA on contact (`k_bip`, default 15) separately toward the league value for that pitch type and cell. The league prior is only as good as the CSV you pass, so include many hitters.
- **Two baselines** on `Hitter`, because they are different scales: `baseline_cq` (from `model.hitter_cq`) drives GO/NO_GO thresholds in `generate_grid_plan`, and `baseline_xwobacon` (from `model.hitter_xwobacon`) is what `evaluate_pitch` compares a batted ball against.
- Plan thresholds are relative to `baseline_cq`: GO at +15%, NO_GO at -20% (`plan.GO_REL`, `plan.NO_GO_REL`). Starting values.

## Validation (`validate.py`)

```
python -m gameplan.validate data/*_2025.csv
```

Per hitter: fit on the first 60% of swings (by date), score the last 40%. League prior comes from other hitters' training swings only. Reports whether held-out swings in GO cells out-produce NO_GO cells, and whether a hitter-specific plan separates them better than a league-only plan.

### Result on 15 hitters, 2025 (Soto, Judge, Arraez, Witt, Ohtani, Freeman, Betts, Ramirez, Henderson, Tucker, Carroll, Marte, Turner, Guerrero Jr., Rodriguez)

- GO cells beat NO_GO cells on held-out swings for 8/8 hitters with enough swings in both groups (mean gap +0.61 of baseline CQ). 7 hitters lacked 30 held-out swings in NO_GO cells; hitters rarely swing at pitches they should not.
- A league-only plan separates almost as well: the hitter-specific plan beat it for 5/8 hitters, mean improvement +0.02. Most of the separation is shared location effect (everyone whiffs on chase pitches).
- Split-half correlation of each hitter's deviation from league: median r = +0.31, positive for 11/15 hitters, range -0.55 to +0.55 on about 12 cells each. Suggestive, not confirmed.

## Architecture (v0.3)

1. **Capability x arsenal** (`shape.py`): kernel model of whiff, foul, xwOBA on contact and squared-up over (location, velo, IVB, HB, VAA), fit on the hitter's own swings and shrunk to a league prior. Starter arsenals (`build_arsenal`) by time through the order, shrunk toward his all-innings shape.
2. **Decision layer** (`decision.py`): swing EV minus take EV in the current count, wOBA scale, using count values fit from data. GO / NO_GO falls out of the count. Base-out / score / inning enter through `SituationWeights` (unvalidated heuristics).
3. **Plans and snapshots** (`matchup.py`): `build_plan` for one situation, `level` = GAME (pregame card, one per hitter per TTO) or PA / PITCH (live). Each build is an immutable, hashed `PlanSnapshot` with its inputs. `review_pitch` scores a pitch against the plan in force and labels it: followed, hitter beat model, deviation cost, umpire miss, or plan silent. `PlanMode.DEVELOP` holds a hitter's own damage zone fixed against a reference arsenal, situation-blind.
4. **Study** (`study.py`, output in `docs/study_2025.txt`): out-of-sample tests on 145 qualified 2025 hitters and 52 qualified starters, fit before 2025-07-01, scored after.

## Study results (2025, MLB Savant)

- Hitter ability is stable enough to plan on: split-half r = .89 whiff, .76 xwOBAcon, .55 squared-up, .52 CQ.
- Held-out swing prediction: hitter data adds real skill for whiff (+1.7% Brier, CI +1.4 to +1.9) and squared-up (+0.9%), a small amount for xwOBAcon (+0.8%). Pitch shape without hitter data adds almost nothing (+0.5% whiff, xwOBAcon and squared-up CIs include 0).
- Count-aware GO / NO_GO is validated: removing count awareness costs S = -0.005 (CI -0.009 to -0.0005) on 127 starters.
- Hitter individualization shows up only where it should. On pitches where the hitter model disagrees with the league model, swinging beats taking by 0.065 wOBA points more in hitter-GO than hitter-NO_GO pitches (CI +0.015 to +0.106; n about 200 pitches each). Overall S does not move (+/-0.003) because the location and count structure dominates it.
- TTO: starters lose only 0.36 mph and 0.07 fastball share from TTO1 to TTO3+, and a TTO-specific arsenal did not improve separation over the all-innings arsenal. A residual TTO effect on contact quality appeared in one held-out cut (+.027 xwOBAcon TTO1 to 3+) but not in training data, so it is not in the plan. Treat TTO as unproven here, not disproven: 52 starters, one season.
- Not tested: base-out and score weights, DEVELOP mode value, and any Single-A data.

## v0.4: situation policy, pitcher state, low-data validation

**Switchable, not assumed.** Every judgment call is a setting a coach or analyst can change, and every plan snapshot records the settings and the pitcher state.

- **Base-out policy** (`decision.SituationConfig`): per spot (runner on third < 2 outs, runners in scoring position with 2 outs, double-play spot, other) choose OFF, MILD (half the fitted change), STRONG (full fitted change) or CONTACT_FIRST (full change, and a GO also needs predicted whiff <= `contact_first_max_whiff`). The change is not a guess: `baseout.py` fits how each state changes the value of a strikeout, a walk and a ball in play from Statcast run expectancy (`baseout_2025.json`). Example: runner on third, one out: K -0.16, ball in play +0.09 wOBA points, and the K figure replicates across both halves of the season. `matchup.recommend_policy` suggests a policy from the hitter's in-zone whiff exposure to this starter; the coach overrides. Score and inning are accepted but not modelled (needs a win-expectancy fit).
- **Pitcher state** (`shape.PitcherState`): TTO, pitch count, live fastball drift, prior PAs vs him today, days of rest, inning. Arsenal basis is switchable (`ArsenalBasis`: ALL_INNINGS, TTO, PITCH_COUNT), with optional live velocity drift. Usage is also conditioned on batter side and strike count via `matchup.arsenal_for_pa`: fastballs are 62.5% of a starter's pitches at 0 strikes and 48% at 2, a bigger swing than TTO (59.7% to 52.7%).
- **Review flags** (`matchup.Review.research_flags`): "good decision that lost" is not defined yet. Candidate definitions are recorded side by side (good take called a strike in zone or by umpire miss, good swing hard-hit out, good swing lucky hit, ...) so the definition can be chosen from data later.
- **Data profiles** (`profiles.py`): per park, which fields exist (location, velo, shape, exit velo/launch angle, bat tracking, pitcher state) maps to a tier and to `ContactModel` settings. Per-system offsets are placeholders that must be estimated before pooling TrackMan and Hawk-Eye data.
- **Coach-report priors** (`coach.py`): tags by pitch family, height and side shift the league prior; the hitter's own swings then override. `trust` scales them.

### What the 2025 MLB data says (docs/study_fatigue_2025.txt, docs/study_lowdata_78.txt)

- **Fatigue drivers** (127 starters, 3,404 starts; docs/study_2025_starters.txt). Within a start, fastball velocity falls about 0.11 mph per 25 pitches (CI -0.16 to -0.06) and 0.15 mph by TTO3+; the slower and faster halves of starters decline about equally (-0.13 and -0.10 per 25 pitches). An earlier 52-starter run suggested slower arms fade more; that did not hold up. Hitter results beyond location and shape barely move with velocity drift, days of rest or pitch count. With TTO alone, hitters whiff less (-0.012 at TTO2, -0.019 at TTO3+, CIs exclude 0) and contact quality is unchanged (+0.004, +0.007, CIs include 0). TTO, pitch count and prior PAs are correlated .93 to 1.00, so this data cannot say which one is the cause, and the joint-regression coefficients (which show pitch count negative and TTO positive) should not be read as separate effects.
- **Feature ladder** (skill vs a league, location + pitch type model): a location-only hitter model beats a pitch-type hitter model for whiff (+2.4% vs +1.5% Brier). Splitting a small hitter sample by pitch type costs more than it gains; pooled location plus shape is best for contact quality (+0.8%). Without exit velocity and launch angle (actual wOBA instead of xwOBA), contact-quality skill drops from +0.4% to -1.6%: quality-of-contact prediction needs batted-ball data, whiff prediction does not.
- **Learning curve** (hitter-specific vs league-only, whiff Brier skill by swings available): N=50 +0.2% (shape +0.7%), N=100 +0.4% (+0.8%), N=200 +0.7% (+1.0%), N=400 +1.2% (+1.4%). Contact-quality skill is near zero until about 200 swings (shape model: +0.4% at 200, +0.6% at 400). Early in a Low-A season, league priors carry most of the load.
- **Coach reports** (simulation of the mechanism, not of any real coach): at 50 swings, a report correlated .7 with the hitter's true tendency helps (+1.7% whiff skill), .5 is neutral, and .3 or an uninformative report hurts (-1.3%, -3.8%). Scaling the report by `trust` = its accuracy turns every case into a gain (+0.6%, +1.1%, +2.1% for .3, .5, .7). Track each coach's reports against the tracked data and set `trust` from that.

## v0.5: policy book, score and inning, coach-report ledger, starters only

- **Policy book** (`decision.PolicyBook`): situation policies at four levels (team default, per opposing starter, per hitter, per hitter-vs-starter pair). Overrides set only the fields they name; later levels in `precedence` win field by field (default: starter, then hitter, then pair). `resolve(hitter, starter)` returns the config used for the plan and `explain(hitter, starter)` says which level set each field. JSON in and out (`to_json` / `from_json`) so coaches can keep it in a file.
- **Score and inning** (`baseout.fit_score_inning`, `scoreinning_2025.json`): for each lead bucket x inning bucket, leverage is the win-expectancy change per run; an outcome's win-expectancy change divided by that leverage is its run-equivalent value in context. Its excess over the plain run value, relative to the all-context average, is the adjustment (wOBA points). The walk adjustments replicate across both halves of the season (late and close or ahead: about -0.05 to -0.11); strikeout and ball-in-play adjustments are small (mostly under 0.04). Buckets with leverage under 0.04 win probability per run (blowouts) get no adjustment. Own policy switch: `SituationConfig.score_inning` (default MILD).
- **Coach reports** (`coach_reports.py`): CSV template with pitch family, height, side, whiff and contact deltas, confidence. `CoachLedger.score` compares a report with the hitter's tracked deviation after the report date, fits how much of the stated deviation shows up (slope through the origin), shrinks toward a 0.3 prior until a coach has about 20 or more scored cells, and returns separate whiff and contact trust. `merge_reports` scales each tag by its coach's trust before it enters the model.
- **Starters only** (`shape.filter_starts`): pitcher-games that began in the 1st inning. Arsenals, TTO, pitch-count states and the studies use starts only; relief outings are excluded.
- **Plan card** (`python -m gameplan.card ...`): builds a real plan from data and prints a per-pitch-type GO / take grid, the model's policy recommendation and the situation weights in force.

### Starters-only rerun (127 starters, 65k pitches, 145 hitters): what changed vs the 52-starter run

- Count awareness still earns its place (S -0.005, CI -0.009 to -0.0005, when removed).
- Hitter individualization still shows up only where the hitter model disagrees with the league model: swinging beats taking by 0.058 to 0.064 wOBA points more in hitter-GO than hitter-NO_GO pitches (CIs +0.016 to +0.095 and +0.034 to +0.094; about 200 to 400 pitches per cell). Overall separation does not move (+/-0.001).
- Shape-aware arsenals, TTO-specific arsenals and a TTO shift still do not improve plan separation. The held-out TTO calibration is flat (xwOBAcon actual minus predicted: -0.015, -0.007, -0.012 at TTO 1, 2, 3+), so the earlier hint of a familiarity gain in contact quality is not there at this sample size. TTO enters the plan only as the small whiff effect above, behind a switch (`apply_tto_effect`, default off).

## v0.6: MLB validation on real outcomes (`validate_mlb.py`, output in docs/validate_mlb.txt)

Held-out 2025 (after 2025-07-01), 145 hitters, vs starters only, cluster bootstrap by hitter.

| Component | Test | Result | Status |
|---|---|---|---|
| Called-strike surface | Brier on 84k taken pitches | fitted by strike count 0.0476 vs stand-in 0.0530 (borderline 0.132 vs 0.147); borderline strike rate by strikes fitted .578 / .443 / .330 vs actual .584 / .436 / .333 | validated, now the default via `zone.CalledStrikeModel` |
| Swing EV | calibration by decile, 32k swings | slope 1.009 (CI .957 to 1.068), every decile within .017 | validated |
| Take EV | calibration by decile, 35k takes | slope 0.993 (CI .984 to 1.001), every decile within .004 | validated |
| Hitter data | year over year, fit on 2024, score 2025 (135 hitters) | whiff +1.8%, xwOBAcon +0.65%, squared-up +0.8% vs a league model; 2024 plus early 2025 is best (+2.4%, +1.0%, +1.2%) | validated |
| Count awareness | S, run value | see v0.5; removing it costs S | validated |
| Base-out weights | S_RV vs real delta_run_exp | paired difference vs count only within +/-0.003 in every spot (runner on 3rd < 2 outs: -0.002 MILD, -0.003 STRONG, CIs include 0). On the few pitches whose call changed (50 to 350 of 61k) the gain is not distinguishable from 0 | not validated; no evidence of harm. Kept as coach options, default MILD |
| Score / inning weights | same | -0.098 [-0.180, -0.008] on the pitches it changed (MILD), STRONG not distinguishable from 0 | not validated; **default set to OFF** |
| Hitter compliance | GO / NO_GO pitches | hitters swing at 71% of GO pitches and take 70% of NO_GO pitches; swinging beats taking by +0.069 runs on GO pitches and -0.118 runs on NO_GO pitches (selection-biased, a ceiling not a forecast) | descriptive |

What this means: the count-aware decision layer is calibrated and adds real value; hitter-specific data helps, including when it comes from the previous season. The base-out and score/inning adjustments come from real run values but do not show up as better calls in outcomes, so treat them as a coach's strategic preference, not a model improvement.

## v0.7: corrections after the methodology audit (docs/METHODOLOGY_AUDIT.md)

Numbers that were wrong, now fixed:
- **wOBA scale** 1.2 -> 1.257 (FanGraphs 2025), via a constants registry (`constants.py`) where every number carries source and status (VERIFIED / DERIVED / CHOICE / BLUEPRINT) and tests pin the verified ones.
- **Realized values** now use the published FanGraphs 2025 weights on the event, not Savant's `woba_value`, which uses rounded legacy weights (walk .7, single .9, HR 2.0) and, when averaged over all events, includes intentional walks and sacrifice bunts. League wOBA computed the published way is .3157 vs FanGraphs .314 on 712,528 pitches / 2,430 games (complete regular season).
- **Count values, base-out and score/inning tables** refit on every plate appearance in the league (not 145 qualified hitters). V(0,0) is now .316 (was .341, an artifact of selection plus rounded weights). Count run values vs published: 0-0 strike -0.038 (-0.037), 0-1 ball +0.023 (+0.024), 1-1 strike -0.060 (-0.054); max relative error 10%.
- **Data handling:** foul tips are whiffs (3,328 of them were fouls), bunts excluded, balls in play without Savant xwOBA dropped instead of filled with actual wOBA. Switches remain to reproduce the old behaviour.
- **Blueprint scoring removed:** decision value in runs (expected value of the action taken minus the alternative, from the plan snapshot) replaces the 100/25/0 scores; execution is reported from measured Statcast fields (attack angle, bat speed, squared-up) plus an angle-mismatch flag, not scored (mismatch has only a weak relation to squared-up, r = -0.06, top-quintile 61.8% vs 69%). The velocity rule (`adjust.py`) is gone.
- **Hitter-level (empirical-Bayes) term** added to the hitter model after a cloud experiment (docs/study_hier.txt): whiff skill vs league-only at N = 50 / 100 / 200 / 400 swings went from +0.14% / +0.25% / +0.48% / +0.86% (local only) to +0.9% / +1.2% / +1.8% / +2.3% (k_global 150); contact-quality skill roughly doubled.
- **Statistics:** two-way (hitter and pitcher) cluster bootstrap, Holm and Benjamini-Hochberg adjustment over the headline tests (`stats.py`).

Built from the audit's plan:
- **Success scorecard** (`success.py`, `docs/scorecard.md`): 17 pre-registered pass criteria across the seven measures (numbers, calibration, skill, separation, actionability, pilot power, honesty). Studies write their headline numbers with `record()`. The six published-benchmark criteria pass on league-wide data: wOBA scale, league wOBA error .0017, TTO1 to TTO2 +6.9 points (published 8 to 13, accepted band 5 to 16), four-seam IVB 15.8 in (published about 16), curveball -10.3 (about -10), count run values within 10%.
- **Plan uncertainty:** each cell carries a standard error and the hitter's effective swing count; a cell is called only if its 90% one-sided bound stays on its side of zero; thin cells are marked `?` on the card and withheld.
- **Plan opportunity** (`opportunity.py`): the starter's location distribution and the hitter's own swing rates give the expected runs per 100 pitches from following the calls (an upper bound, selection-inflated), by pitch type and cell.
- **Pilot design** (`docs/PILOT_DESIGN.md`, `pilot.py`): sample-size arithmetic (0.017 runs per pitch detectable at 2,500 pitches per arm), stepped-rollout power simulation, split-half reliability of candidate process metrics.
- **League-wide data path:** `python -m gameplan.bulk --league data/league` pulls every pitch of a season (about 4,500 a day); studies accept it, so the league prior comes from all hitters and starters from all pitchers.

Cloud runs still in progress when this was written (results land on branches `claude/league-validation-results` and `claude/audit-league-results`): the full corrected rerun on all hitters and starters, calibration by segment, hyperparameter and split-date sensitivity, data-handling effects, and the confidence-bound test. Until they are in, the scorecard rows for measures 2 to 7 read NOT MEASURED and every number in the earlier v0.5 and v0.6 sections that predates this section was computed on the pre-fix data.

**Bug found later the same day (D8):** Savant's `api_break_x_batter_in` is in feet, not inches (SD 0.86 ft), so the horizontal-break dimension of the shape model was effectively switched off in every study so far that used shape mode. Fixed (`savant._hb_in`, tested). Results for shape-aware models in the sections above, including "shape alone adds almost nothing", were computed without horizontal break and have to be treated as unmeasured until the rerun. Cloud runs started before the fix were stopped and restarted.

## MiLB loader (`milb.py`, `evla.py`, `profiles.py`)

Adapter from an organization's export to the Savant-style CSV every study and the card already read. `python -m gameplan.milb --export export.csv --map columnmap.json --out converted.csv --park Visalia`.

- **You declare the mapping** (`examples/milb_columnmap_example.json`; the source column names there are placeholders, not a claim about any vendor's export): which column is which canonical field, units (ft / in / cm / m, mph / kph / mps), value maps (calls, handedness, pitch types), whether horizontal break is catcher-view or batter-relative, and the plate-x sign.
- **Nothing silent:** unmapped call codes stop the run (or are counted with `--lenient`), missing required fields and columns raise, rows without handedness or location are counted.
- **Unit check against MLB:** every converted field's SD and mean are compared with the 2025 MLB reference (`field_reference_mlb_2025.json`). A unit error such as break in feet read as inches shows up as an SD ratio near 12 and is flagged; this is the check that would have caught the horizontal-break bug.
- **Derived state:** times through the order and prior plate appearances vs the pitcher come from the pitch sequence (they match Savant's `n_thruorder_pitcher` for the same plate appearances).
- **Expected wOBA:** if the export has no expected-stats field but has exit velocity and launch angle, xwOBA is filled from an MLB lookup (`xwoba_evla_2025.json`) and flagged `evla`. Held-out check on 40,254 MLB balls in play: correlation 0.979 with Savant's xwOBA, mean absolute error 0.052, bias -0.0003.
- **System offsets:** `estimate_offsets` gives the mean difference and standard error between two systems measuring the same pitches, to store as `DataProfile.offsets` (plate location, IVB, HB, velocity). None are assumed.
- **Tier:** `infer_profile` reads the mapping and returns the data tier and the `ContactModel` settings that tier supports (full shape, velocity-only, or location and type with actual wOBA in place of xwOBA).

What this does not settle: how each park's system actually differs from Savant's Hawk-Eye. That needs overlapping measurements (a Triple-A park that reports to Savant, or pitches captured by two systems), not a config file.

## v0.8: corrected league-wide validation (docs/validate_league.txt, study_league.txt, audit_checks_league.txt, scorecard.md)

Data: every 2025 regular-season pitch (712,528 pitches, 2,430 games); 673 hitters, 375 starters (4,882 starts); horizontal break fixed, hitter-level term on, published wOBA weights, two-way (hitter and pitcher) bootstrap. **Scorecard: 15 pass, 1 fail, 1 not measured** (`docs/scorecard.md`).

What held up:
- **Calibration** of the two halves of the decision layer, held out, vs starters: swing EV slope 1.023 [0.973, 1.076], take EV slope 0.992 [0.984, 0.999], every decile within 0.014 wOBA points. Called-strike surface by strike count matches actual borderline strike rates (0.581 / 0.444 / 0.352 fitted vs 0.581 / 0.444 / 0.350).
- **Hitter data adds skill** (held out; tests of prediction, not of plans): whiff Brier +2.6% and xwOBAcon MSE +1.3% for the shape-aware hitter model vs a league location-and-type model; year over year (fit only on 2024, score 2025) +2.8% and +0.9%; with 2024 plus early 2025, +3.2% and +1.2%. Stable across four cutoffs (whiff +2.1% to +2.7%, xwOBAcon +1.2% to +1.4%). Hitters differ reliably (split-half r: whiff .84, xwOBAcon .64, squared-up .57).
- **Confidence bounds work:** where the point estimate says GO, pitches whose bound clears zero separate swing from take by +0.054 runs more than thin-support pitches [0.038, 0.068]; for NO_GO +0.066 [0.053, 0.080].
- **Count awareness** earns its place: removing it changes S by -0.0042 runs [-0.0086, -0.0002] (borderline).
- **Published benchmarks** all pass (see v0.7). League-wide TTO: +6.9 wOBA points 1 to 2, +12.9 points 2 to 3+.

What did not hold up, or moved:
- **FAIL, hitter-specific plan calls vs league plan calls** (scorecard measure 4): on pitches where the hitter model and the league model disagree, swing-minus-take is higher in the hitter's GO calls than his NO_GO calls by +0.047 runs [-0.0009, +0.099] under the two-way bootstrap (raw p 0.067, Holm 0.14). The earlier "+0.06, CI excludes 0" used a hitter-only bootstrap; with a hitter-only bootstrap this run also excludes 0 (+0.050 [+0.027, +0.075], Test 3). Prediction-level individualization is established; plan-level individualization is not, under proper clustering and multiplicity correction.
- **Multiplicity:** no headline test is significant after Holm (smallest adjusted p 0.13). Read the individual CIs as descriptive.
- **Shape:** with horizontal break fixed, shape alone adds little (league-only +0.6% whiff, +0.0% xwOBAcon, ns) but combined with hitter data it beats location-and-type by +0.2% whiff and +0.5% xwOBAcon.
- **TTO:** hitters whiff less each time through (actual minus predicted whiff +0.010, -0.006, -0.011 at TTO 1, 2, 3+), contact quality is flat. The plan applies this only behind the `apply_tto_effect` switch.
- **Situation weights:** overall no gain (paired S difference +0.0005 to +0.0007, CI touching 0). On the pitches whose call the weights actually changed, in the spots they target, the promoted pitches did beat the demoted ones: runner on 3rd < 2 outs, MILD +0.059 [+0.004, +0.107] (143 pitches), STRONG +0.050 [+0.013, +0.088] (250); RISP two outs, MILD +0.050 [+0.001, +0.103] (277). These are single-spot subgroup results without multiplicity correction. Score/inning: no evidence either way; stays OFF.
- **Small systematic miscalibration by count and context (C1),** all under the 0.02 criterion but real (CI excludes 0): swing value under-predicted at 3 balls (+0.016) and at 2 strikes (+0.009), take value over-predicted at 3 balls (-0.011); swing under-predicted against breaking and offspeed pitches (+0.005), for right-handed batters (+0.004) and at TTO 3+ (+0.006). At 3-0 and 3-1 these gaps are large enough to matter against the +/-0.02 call threshold.
- **Hyperparameters matter more than I assumed (C2):** halving the kernel bandwidth collapses whiff skill (-3.5%) so the default sits near a cliff edge; whiff prefers bandwidth x2 (+2.9%) and looser shrinkage (x0.25: +2.9%); xwOBAcon prefers the default bandwidth and default or stiffer shrinkage. Neighbour count is irrelevant. A per-target setting could add about 0.3% on whiff.
- **Data-handling fixes (C4):** counting foul tips as whiffs moves the whiff rate per swing from .231 to .253 but changes skill by only +0.17%; bunts and xwOBA-less balls in play are negligible.
- **Pilot (docs/pilot_reliability.txt):** process metrics are usable for hitters over a season: decision value per 100 pitches split-half r .48 (full-length reliability .65), chase rate .64 (.78), zone-swing rate .65 (.79), compliance .49 (.66). Stepped-rollout power for a 0.005-run effect with 12 hitters is 0.14.

Caveat on scorecard measure 6: it passes only at 2,500 pitches per arm (minimum detectable 0.0166 runs); at 250 pitches it is 0.053.


## Run the app on your computer

```bash
git clone <this repo> && cd GamePlan
pip install -e .
gameplan --download --open     # first run only: downloads the 2025 season of public pitch data, then opens the app
gameplan --open                # every later run
```

The app runs only on your computer (http://127.0.0.1:8765). Pick a game in the library; Build prepares a new one (about 5 minutes, with each hitter's pregame board filling in after). Your saved decisions and skips are stored in `data/app/`.
