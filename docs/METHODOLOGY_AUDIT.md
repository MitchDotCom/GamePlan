# Methodology audit

Purpose: separate what is measured from data, what matches a published reference, and what I chose or invented, then list every hole I can find. Written to be read by the person who has to trust or reject the output, not to defend it.

**Status after the fixes (2026-09-29):** D3, D4, V1, E1, E2, E4, S1 (code), S2 (code), M2, M5 (opportunity), L2 (confidence rule), G1 fixed; D2 fixed by the league-wide refit; the published-benchmark checks pass. Still open: D1 (MLB only), D5, D6, D7, V2 to V6, M1, M3, M4, L1, L3 to L5, E3, the coach-report holes, S3 to S6 and G2 to G3. M1, M3, S4 are being tested in the cloud. See the README v0.7 section and `docs/scorecard.md`.

Limits of this audit, stated first:
- The primary pages (FanGraphs Library, MLB glossary, SABR, arXiv, Baseball Prospectus) are blocked by this environment's network policy, so I could not open them. Every published fact below comes from web-search result summaries, not from reading the page. Treat "matches the reference" as "matches what a search summary of the reference says" until someone opens the page. Domains to allow so I can read them directly: `library.fangraphs.com`, `blogs.fangraphs.com`, `www.mlb.com`, `sabr.org`, `arxiv.org`, `www.baseballprospectus.com`, `tangotiger.net`, `www.baseball-reference.com`.
- Two cloud runs were still in progress when this was written (hitter-level term experiment; segment calibration, sensitivity and data-handling checks). Results go in `docs/study_hier.txt` and `docs/audit_checks.txt` on branches `claude/hier-experiment-results` and `claude/audit-checks-results`. Sections that depend on them say so.

## 1. What the system claims to do, and for whom

**User:** a hitting coach or player-development staffer who will hand a hitter a plan ("sit on this, take that") before a game or before an at-bat, and later judge whether the hitter followed it and whether it helped.

**Claim:** given a hitter's tracked history and a starter's arsenal, the engine returns, per pitch type and location, whether swinging beats taking for this hitter in this count.

**What the user needs to be able to trust:**
1. The value of a swing and of a take are right on average and in each situation they will use (count, pitch type, handedness).
2. The hitter-specific part is real, not noise, at the sample sizes they actually have.
3. The plan, followed, produces better outcomes than what the hitter does now.
4. The output says when it does not know.

Points 1 and 2 are testable on MLB data and mostly tested. Point 3 has not been tested at all. Point 4 is not built.

## 2. Value-by-value provenance

Status key: **VERIFIED** matches a published definition or value; **DERIVED** fit from Savant 2025 data by code in this repo; **CHOICE** my setting, no source; **BLUEPRINT** came from the original spec, no source; **WRONG** contradicts a reference.

| Value | Where | Status | Evidence |
|---|---|---|---|
| Squared-up = EV / (1.23 x bat speed + 0.2116 x pitch speed) >= 0.80 | `savant.py` | VERIFIED | MLB glossary definition as summarized in search results; also Yahoo, NBC. Not checked against Savant's own squared-up column (not in the export). |
| Vertical approach angle from vy0, vz0, ay, az, y0=50, yf=17/12 | `savant.py` | VERIFIED | Same equations as the FanGraphs VAA primer (search summary). Sign convention matches (negative = descending). |
| IVB = pfx_z x 12 | `savant.py` | VERIFIED in concept, unverified numerically | MLB glossary: IVB is movement with gravity removed. Savant's `pfx_z` is the no-gravity component. Sanity: my curveball IVB reads -10.3 in vs the published 2024 league average of about -10; four-seam +15 vs +16. Not compared per pitcher. |
| xwOBA on contact | uses Savant's `estimated_woba_using_speedangle` | VERIFIED (not mine) | Savant's model (exit velocity, launch angle, sprint speed on some balls). I do not compute xwOBA. 341 of 61,035 balls in play have none; I fill with actual wOBA (see D4). |
| wOBA scale 1.2 | `baseout.py` | **WRONG** | FanGraphs 2025 constants: wOBA scale 1.257, league wOBA .314, wBB .693, wHBP .725 (search summary of the Guts page). 1.2 understates every base-out and score/inning adjustment by about 4.5%. |
| Walk value .70, HBP .72 | `decision.py` | VERIFIED | Walk fit from data at .70 vs FanGraphs .693; HBP .72 vs .725. |
| Count values V(balls, strikes) | `count_values_2025.json` | DERIVED, partly verified | Method matches Savant/BP: outcome value by count. Numeric check: 0-0 strike -0.038 runs (published -0.037), 0-1 ball +0.021 (+0.024), 1-1 strike -0.059 (-0.054). 1-2 not comparable (published figure averages foul balls and strikeouts). Level problem: fit on 145 qualified hitters, so V(0,0) = .341 vs a league wOBA of .314 (see D2). |
| Base-out adjustments (K, walk, ball in play by state) | `baseout_2025.json` | DERIVED | Mean `delta_run_exp` on the last pitch by state minus all-states mean, x scale. Method is my own construction; not a published metric (see V5). Failed outcome validation. |
| Score/inning adjustments and leverage | `scoreinning_2025.json` | DERIVED, non-standard | Leverage here is a regression slope of win-expectancy change on run-expectancy change. FanGraphs/Tango Leverage Index is different (expected swing in win expectancy / average). Failed outcome validation; off by default. |
| Called-strike surface | `zone.py` | DERIVED | 95k taken pitches before July 1; held-out Brier .0476. Count effect direction matches published umpire findings (more strikes in hitter's counts, more balls in pitcher's counts). |
| Time-through-order effect on wOBA | reproduced in `docs` check | DERIVED, matches literature in direction and rough size | My sample: +6.4 wOBA points TTO1 to TTO2, +4.0 TTO2 to TTO3+ (qualified hitters vs 127 starters). Published: about +8 to +13 per time through (Tango/Lichtman; Bayesian analysis +13.4 first to second); pitchers with mostly fastballs lose more. |
| Stabilization / shrinkage: k_whiff 25, k_xw 12, k_su 12, K_hitter 80, K_league 400, prior_m 3 | `shape.py` | **CHOICE** | Not derived. Published stabilization points are far larger (K% about 60 PA, contact% about 100 PA, per Carleton via FanGraphs Sample Size). Tested only at x0.5 and x2 in the learning curve. Sensitivity check pending (C2). |
| Kernel bandwidths 0.30 ft, 3 mph, 4 in, 4 in, 0.8 deg | `shape.py` | **CHOICE** | No cross-validation. Sensitivity check pending (C2). |
| GO / NO_GO threshold +/-0.020 wOBA | `decision.py` | **CHOICE** | No basis. |
| Policy scale MILD 0.5, STRONG 1.0; SHRINK_N 100; MIN_LEVERAGE 0.04; contact-first whiff cap .22; K-risk cutoffs .27/.21 | `decision.py`, `matchup.py` | **CHOICE** | No basis. |
| Decision scores 100/25/0/60/40, good-decision 75 | `evaluate.py` | **BLUEPRINT** | Unsupported. Should be replaced (see E1). |
| Execution penalties 4.0 per degree, 2.5 per ms; target angle = -pitch VAA; good execution 60 | `evaluate.py` | **BLUEPRINT** | Unsupported and untested. "Timing error in ms" is not a public Statcast field I could identify. |
| Velocity drift rule: 2.5 mph trigger, 1 inch per mph, max 4 | `adjust.py` | **BLUEPRINT** | Unsupported. My own fatigue study found velocity drift has no measurable effect on hitter results. |
| Coach ledger prior 0.3, strength 20; coach-form size anchors 0.03 / 0.06 / 0.10 | `coach_reports.py`, form | **CHOICE** | The anchors were never compared to how much real hitters actually differ from league. |
| Cutoff 2025-07-01 | all studies | **CHOICE** | One split only (see C3). |

## 3. Holes, by layer

Severity: **Critical** (invalidates a headline claim), **High**, **Medium**, **Low**. "Open" means not yet tested; "Pending" means a cloud run will answer it.

### A. Data and measurement

| # | Hole | Sev | Status |
|---|---|---|---|
| D1 | Everything is MLB Hawk-Eye data on qualified hitters and qualified starters. Survivorship: full-time players against a rotation. Nothing here says the results transfer to Single-A, where hitters have fewer swings, pitchers have less stable arsenals, and tracking systems differ. Published notes say TrackMan (radar) and Hawk-Eye (optical) measure extension and release differently, so pooled MiLB data needs per-system offsets I have not estimated. | Critical for MiLB | Open |
| D2 | Count values and base-out tables are fit on qualified hitters only, so absolute values sit above league (V(0,0) .341 vs FanGraphs 2025 wOBA .314). Differences between actions are less affected, but the levels feed EV comparisons. | High | Open |
| D3 | 3,328 foul tips are treated as fouls. Published plate-discipline definitions treat a foul tip as a swinging strike, and with two strikes it is strike three. That understates the whiff rate by roughly 9% of whiff-like events and misvalues those pitches in the count. | High | Pending (C4) |
| D4 | 450 bunt swings and 132 bunt plate appearances are in the swing data; 341 balls in play with no Savant xwOBA fall back to actual wOBA, mixing an expected and an actual scale. | Medium | Pending (C4) |
| D5 | The "starter" list is the Savant pitcher leaderboard at `min=100`. I never confirmed what unit that is (innings, batters faced, pitches). The 127 pitchers include whoever the leaderboard returns; only their 1st-inning-start outings are kept. | Medium | Open |
| D6 | Pitch classification labels (ST vs SL, SV, FS) are Savant's and change over time; the shape mode ignores labels but the type mode and arsenals depend on them. | Low | Open |
| D7 | Not modelled at all: umpire, catcher, park, weather, pitcher handedness beyond batter-relative coordinates, pitch sequence and tunnelling, extension and release height as deception, whether the batter is a switch hitter facing his weaker side. | High | Open |

### B. Value framework

| # | Hole | Sev | Status |
|---|---|---|---|
| V1 | wOBA scale is 1.2; the published 2025 value is 1.257. Every base-out and score/inning adjustment is about 4.5% too small. | Low (those adjustments did not validate anyway) | Open, trivial fix |
| V2 | A ball in play is valued at xwOBA regardless of base-out state: no sacrifice fly, no double play, no runner advancement. Savant's and Tango's run values use base-out-count states (RE288) so those consequences are in. | High | Open |
| V3 | The count table is an average-hitter table used for every hitter. A high-strikeout hitter's 0-2 count is worth less to him. Savant's swing/take uses league count values too, so this is standard, but it biases decisions for extreme hitters. | Medium | Open |
| V4 | Take EV ignores the information value of a look at the pitch and the effect of the take on the pitcher's next pitch. | Medium | Open |
| V5 | The situation adjustments are my construction. The published approach is either context-neutral run value (Savant's default) or the same values weighted by leverage. Mine combines wOBA-scale count values with adjustments estimated from run-expectancy deltas, mixing two scales. They failed the outcome test. | High | Tested, failed |
| V6 | The calibration test (V2 in `validate_mlb`) values realized outcomes with the same count table used to predict them, so it validates the outcome probabilities (whiff, foul, contact, called strike), not the count table itself. The count table is checked only by the four published numbers above. | Medium | Open |

### C. Hitter and pitcher models

| # | Hole | Sev | Status |
|---|---|---|---|
| M1 | The swing model ignores the count. Approach changes with two strikes (shorter swing, more fouls, fewer whiffs). Predicted swing value is pooled over counts. Overall calibration passes but it can be wrong at specific counts, where the decision is made. | High | Pending (C1) |
| M2 | No hitter-level (global) term. The published small-sample method is empirical Bayes: shrink the hitter's overall rate to the league first (stabilization about 60 to 100 PA for K% and contact%), then local deviations. The current model shrinks each neighbourhood to the league on its own, so a hitter's overall tendencies are learned slowly from local data. | High for low-N (Low-A) | Pending |
| M3 | Bandwidths and shrinkage strengths are hand-chosen. Reported skill may depend on them. | High | Pending (C2) |
| M4 | Neighbour caps (80 hitter, 400 league) and `prior_m` make effective sample size depend on data density, not on a stated stabilization target. | Medium | Pending (C2) |
| M5 | The arsenal is the mean shape per pitch type. It ignores where the pitcher throws (his location distribution), so the plan can call GO in cells he never throws to and never weights cells by how often the pitch arrives there. The expected value of following the plan is therefore never computed. | Critical for a usable plan | Open |
| M6 | TTO cannot be separated from pitch count (correlation .93 to 1.00 in this data), which matches the literature's own caveat that batter learning and fatigue cannot be disentangled with existing approaches. The switchable basis is honest; the plan effect is unresolved. | Medium | Documented |
| M7 | Held-out swings cover July to September only; hitters' early-season swings train them. Seasonal drift (weather, injuries, swing changes) is unmodelled. | Low | Open |

### D. Decision layer

| # | Hole | Sev | Status |
|---|---|---|---|
| L1 | The plan is by pitch type and location, which assumes the hitter identifies the pitch in time. Recognition and reaction windows were in the original spec (175 to 220 ms) and were never validated here. A plan he cannot execute has no value. | Critical for a usable plan | Open |
| L2 | Threshold +/-0.02 is a choice, and ignores uncertainty: a cell is GO on a point estimate with no confidence requirement. | High | Open |
| L3 | Static plan: no model of the pitcher adapting to what the hitter does (equilibrium). | Medium | Open |
| L4 | Every "swing minus take" result is observational: hitters choose what to swing at. The +0.069 / -0.118 run gaps are upper bounds on any effect of following the plan and could be pure selection. | Critical for claim 3 | Open |
| L5 | No causal evidence that following the plan improves outcomes. Per-pitch run value has an SD of about 0.33 runs on swings; detecting a 0.016-run per-pitch difference at 80% power needs about 2,500 pitches per arm, and 0.005 needs about 25,000. A single hitter over one season cannot show it. | Critical for claim 3 | Documented; needs a design |
| L6 | Base-out and score/inning policies are unvalidated (see V5). | Medium | Tested |

### E. Scoring and review (`evaluate.py`, `matchup.review_pitch`, `adjust.py`)

| # | Hole | Sev | Status |
|---|---|---|---|
| E1 | The 100/25/0/60/40 decision scores come from the spec. The published equivalent is decision value: expected value of the action taken minus the alternative, in runs (Savant swing/take; TJStats batter decision value). Replace with that. | High | Open |
| E2 | The execution score has no support: target angle = -pitch VAA is an assumption, "timing error in ms" is not a public field I could find, penalties are invented. Savant publishes squared-up, swing length, attack angle and miss distance; use those and validate. | High | Open |
| E3 | Quadrant boundaries (75, 60) and the dev-assignment mapping are arbitrary. | Medium | Open |
| E4 | `adjust_plan` velocity rule is unsupported and contradicted by the fatigue study. | Medium | Open |

### F. Coach reports

| # | Hole | Sev | Status |
|---|---|---|---|
| C1c | The simulation of report accuracy used emulated reports built from the hitter's own true tendencies; it shows the mechanism, not that coaches are accurate. The trust prior (0.3, 20 cells) is unvalidated. | Medium | Documented |
| C2c | Reports are scored on my cells (pitch family x height). Coaches think in other terms (velocity, sequencing, "late on heat"); mapping loses information and the scoring only rewards what maps. | Medium | Open |
| C3c | The size anchors on the coach form are guesses. | Medium | Open, quick data check available |

### G. Statistics

| # | Hole | Sev |
|---|---|---|
| S1 | Bootstrap resamples hitters only. Pitchers, games and umpires are also clusters; intervals are probably too narrow. | High |
| S2 | Dozens of tests, no multiplicity correction. Some intervals that exclude zero are expected by chance. The individualization result (the disagreement test) is the one most exposed. | High |
| S3 | Count and base-out tables were fit on the full season including the test period. Only the base-out and count checks are affected, and the situation weights still did not help, so the bias is not what hid a benefit. | Low |
| S4 | One split date (C3 pending). | Medium |
| S5 | Reported skill gains (+1% to +2% Brier, +0.5% MSE) have no translation into runs or into a decision that changes. | High |
| S6 | Selection of test hitters: those with 400+ training swings, excluding part-time and rookie profiles, the same group the tool is meant for at Low-A. | High for MiLB |

### H. Engineering

| # | Hole |
|---|---|
| G1 | Constants are scattered with comments, not a registry. Nothing in the tests pins a constant to its source. Proposal: a `constants` module where each entry carries source, retrieval date, and verification status, and a test that fails if a VERIFIED constant changes. |
| G2 | The data come live from Savant; revisions to past seasons would change results silently. Pull snapshots should be hashed and recorded with each study output. |
| G3 | Unit tests use synthetic data. Nothing regression-tests the published benchmarks (wOBA weights, count values, TTO penalty). |

## 4. What "success" means, in order of what can be measured now

1. **Numbers are right.** Constants match sources (registry + tests). Count values and wOBA weights reproduce published values within a stated tolerance every season.
2. **Probabilities are calibrated.** Predicted swing and take value against realized, overall (done: slopes 1.009 and 0.993) and per segment (pending C1), on a rolling basis.
3. **Hitter data adds skill.** Held-out prediction beats league-only, including year over year (done: whiff +1.8%, contact quality +0.65%, squared-up +0.8% using 2024 only).
4. **Decisions change and stay separated.** The call differs from a count-only call on a stated share of pitches, and on those pitches realized swing-take gaps move the right way (done only for the hitter-vs-league disagreement, on about 200 to 400 pitches per side).
5. **Hitters can act on it.** Compliance and recognition feasibility measured in a pilot (not started).
6. **It helps.** Needs a design. Per-pitch noise (SD about 0.33 runs on swings) means outcome tests need thousands of pitches per arm. Realistic options: a stepped rollout across many hitters, within-hitter alternating weeks on and off, and process outcomes (swing-decision value per pitch, chase and zone-swing rates, squared-up rate) rather than results.
7. **It says when it does not know.** Each plan should show the sample behind each region and suppress calls the data cannot support. Not built.

## 5. Missing from the design entirely (from the end user's seat)

- Cold start: a starter the hitter has never seen, an arsenal with few pitches, a hitter with under 200 swings. Confidence and fallback behaviour are undefined.
- A readable output: today's card is a plain grid. It does not show sample sizes, uncertainty, or reasons ("because he whiffs 42% on elevated fastballs, n = 61").
- What the coach is asked to do with a NO_GO cell when the pitcher's actual location distribution rarely reaches it.
- Handling of the hitter's own development goals (the develop mode exists, has no validation).

## 6. Recommended order of work

1. Fix the data-handling defects (foul tips, bunts, missing xwOBA) and the wOBA scale; rerun everything; report how much moved (C4 measures this).
2. Replace guessed shrinkage and bandwidths with cross-validated or empirical-Bayes values; add the hitter-level term if the cloud experiment supports it.
3. Build the constants registry with source and verification status; pin the verified ones in tests.
4. Add count as a feature of the swing model if C1 shows count-specific miscalibration.
5. Replace the blueprint scoring (decision score, execution score, velocity rule) with published-style decision value and Statcast bat-tracking measures; validate.
6. Add pitcher location distributions and compute the expected value of following the plan, with uncertainty and sample-size flags on every cell.
7. Correct for clustering beyond hitters and for multiplicity; add a second split date and rolling-origin evaluation.
8. Only then design the pilot.

## Sources (search summaries; primary pages not opened)

- FanGraphs Guts, 2025 constants: https://www.fangraphs.com/guts.aspx?type=cn
- FanGraphs wOBA and linear weights: https://library.fangraphs.com/offense/woba/ , https://library.fangraphs.com/principles/linear-weights/
- Tango run expectancy matrix: https://www.tangotiger.net/re24.html ; swing/take primer: https://tangotiger.com/index.php/site/article/statcast-lab-swing-take-and-a-primer-on-run-value
- Baseball Savant swing/take leaderboard: https://baseballsavant.mlb.com/leaderboard/swing-take?year=2026
- Baseball Prospectus StuffPro/PitchPro: https://www.baseballprospectus.com/news/article/89245/stuffpro-pitchpro-introduction-new-pitch-metrics-bp/
- TJStats batter decision value: https://tjstats.ca/2023/12/01/modelling-batter-decision-value/
- MLB glossary, squared-up: https://www.mlb.com/glossary/statcast/squared-up ; induced vertical break: https://www.mlb.com/glossary/statcast/induced-vertical-break
- FanGraphs VAA primer: https://blogs.fangraphs.com/a-visualized-primer-on-vertical-approach-angle-vaa/
- FanGraphs sample size and stabilization: https://library.fangraphs.com/principles/sample-size/
- Leverage Index: https://library.fangraphs.com/misc/li/
- Time through the order: https://www.baseballprospectus.com/news/article/22156/baseball-proguestus-everything-you-always-wanted-to-know-about-the-times-through-the-order-penalty/ , https://sabr.org/latest/lichtman-the-penalty-for-pitchers-going-through-the-batting-order/ , https://arxiv.org/pdf/2210.06724
- Called strike probability and umpire count effects: https://www.baseballprospectus.com/news/article/31022/prospectus-feature-command-and-control/ , https://bayesball.github.io/BLOG/Called_Strikes.html
- Empirical Bayes for hitters: http://varianceexplained.org/r/hierarchical_bayes_baseball/
- Foul tips in whiff/CSW definitions: https://pitcherlist.com/csw-rate-an-intro-to-an-important-new-metric/
- TrackMan vs Hawk-Eye: https://baseballcloud.blog/2020/08/14/is-hawk-eye-inflating-extensions/ , https://tht.fangraphs.com/theres-lots-of-physics-to-do-now-that-hawk-eye-is-up-and-running/
