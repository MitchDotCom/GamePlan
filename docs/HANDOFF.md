# GamePlan handoff briefing (2026-10-04)

Paste this to another AI or engineer to bring them up to date. Everything here was checked against the repository and the session history; where something is a claim from a research note, it says so.

## 1. What this is, and for whom

A hitter-specific, starter-specific game-plan tool for professional baseball hitting development. For a lineup facing a given starter it shows, per hitter and per count, where to swing and where to take, 1 to 3 distinguishable approach paths, and reviews every pitch afterward against the plan. It also shows whether the hitter can do damage on what he swings at (bat tracking against the starter's arsenal).

- **Owner:** a Player Development Associate with the Arizona Diamondbacks, assigned to the Visalia Rawhide (Single-A, California League). Personal project until the organization approves any use.
- **Mission:** develop hitters first, win second. Hitters only. Starters only (no relievers yet).
- **Target:** a trial at Visalia by Opening Day 2027 (about 26 weeks from 2026-10-02).
- **Data:** public MLB Statcast data first (2024 and 2025 seasons loaded); TrackMan and Hawk-Eye exports later via an onboarding kit. The public data does not include the California League, so real use needs a club-supplied feed.
- **Users and setting (owner's answers, 2026-10-04):** hitting coaches and staff. Use order: dugout tablet, then pregame meeting on a laptop, then postgame video. Approach is mostly verbal at the club today. Success in the first season means hitter development (process metrics), not wins. California League uses human umpires (owner's statement).

## 2. Rules for working with this owner (carry these over)

- Plain, brief, direct. No filler, flattery, preamble or closing summaries. Recommend first. No em dashes. Avoid words like "robust", "seamless", "certainly", "actually".
- Do not do more than asked. When asked for a prompt or a plan, deliver that and stop; do not launch the work. (An unrequested research run on 2026-10-04 was called out.)
- Nothing is adopted into the model until the owner has seen the table of results. Every number must be fitted or sourced with a stated method; unfitted values are labelled CHOICE.
- Long jobs run in the background. The owner dislikes long foreground waits.
- A monitoring rule is in force: call `date` at least every 15 minutes and file a short status report (process, status, progress, next) after each call. No subagents or workflows unattended. Keep reasoning and tests minimal; no invented gates.
- The stop hook requires every change to be committed and pushed. Never open a pull request unless asked.
- Use only openly licensed or published methods. One restricted-license repository is excluded by the owner entirely; do not look for it.
- GitHub work uses the repository `MitchDotCom/GamePlan`, branch `claude/baseball-hitting-strategy-engine-iwo2dz`.

## 3. What exists (features)

**App (local, non-static).** A stdlib HTTP server with a JSON API and a single-page viewer; a pywebview desktop wrapper; a Mac double-click launcher (`GamePlan.command`); a PyInstaller GitHub workflow. Data lives in `data/app/` (games, cache, log). Code: `server.py`, `desktop.py`, `viewer/` (`viewer.html`, `.css`, `.js`), `game_html.py`.
- **Game library** from the day files (home and away team and starters), with an in-app season download.
- **Per-game pages** with tabs: Game (zone-first at-bat review), Pregame (per hitter and count), Hitters, Log.
- **Build on demand** in a separate process (about 5 minutes for the game, then each hitter's pregame board fills in), two builds at a time. Pregame boards load lazily.
- **Model stamp and refresh.** Every finished build writes `stamp.txt` (hash of the build's import chain plus data files). A game with an old stamp shows "Out of date"; the Library's "Update" button or `python -m gameplan.refresh --league data/league --app-dir data/app --preview <file>` rebuilds only those, two at a time, in a staging folder swapped in on success. A killed run resumes by rerunning.
- **Shared preview:** a private hosted copy of the app with four built games (https://claude.ai/artifact/5S3RABHVkVtixjGHVLBtPy), made by `python -m gameplan.preview`. It is read-only; skips and log choices stay in the browser.

**Zone-first at-bat view.** Large strike zone with the hitter's own zone outline (per-pitch top and bottom), numbered pitches by result, a plan overlay per pitch, a stepper, catcher view or batter-relative view. Location geometry is tested against raw rows and umpire called-strike rates (`docs/zone_geometry_check.txt`).

**Skip control.** Bunts, intentional walks, catcher interference, automatic calls and position players pitching are skipped automatically; a pitchout drops only that pitch; a coach can skip or restore any at-bat with a reason. Skipped at-bats leave the totals.

**Pregame board and paths.** For each hitter, count and time through the order: the Value plan (confident calls only), a Contact-capped plan, and "Decide every pitch" (a call on every cell, thin evidence included, labelled less certain). A path shows only when its calls differ from the others on at least 10% of pitches and it is within 1.5 runs per 100 plate appearances of Value (both thresholds are placeholders for a coach to set). Hunt ("sit on a pitch") is built and scored but hidden behind an experimental toggle, because the model cannot value anticipation. Each alternative shows its whole-at-bat value gap to Value with a range.

**Post-game review.** Every pitch is labelled: followed plan, hitter beat the model, deviation cost, umpire miss, plan silent. The plan is silent on about half of pitches; the interface says so.

**Swing and damage lens.** Per-swing bat tracking (bat speed, swing length, attack angle, tilt, exit velocity, launch angle, xwOBA), the hitter's personal whiff-versus-bat-ball-angle curve and band, and a hitter-versus-arsenal table (damage per swing by pitch family and zone group, shrunk toward the league).

**Decision log.** One choice per `date|starter|hitter|time-through-order|count` with path, reason and note, stored server-side; CSV export. (See gaps below.)

## 4. The models and what is proven

All tests are pre-registered with a held-out period and a second-season confirmation (2024). Results are in `docs/`.

| Piece | Where | Status |
|---|---|---|
| Swing versus take value (kernel contact model: whiff, foul, xwOBA on contact; shape and count features; hitter term; called-strike model) | `shape.py`, `decision.py`, `zone.py`, `matchup.py` | Scorecard 15 pass, 1 fail, 1 not measured (`docs/scorecard.md`). The fail: hitter-versus-league disagreement. Not measured: hitters' pitch recognition (needs pilot data) |
| Plate-appearance value (backward induction over the 12 counts) | `pa_value.py` | Reproduces the count table within 3.5% (tolerance 15%) |
| Plane term (league whiff curve at the hitter's expected bat-ball angle) added to the whiff logit | `plane_term.py`, `plane_fit.py` | Passes against the full kernel in 2025 and 2024: +0.0031 and +0.0023 log-loss per swing. Most of the gain is the pitch-conditional angle; the hitter-specific part adds +0.0007 and +0.0005 (small, real). His personal curve shape adds nothing once his expected angle is in. Adopted for whiff prediction only |
| Bat speed, swing length, attack angle alone | `swing_traits.py`, `traits_test.py` | Fail on whiffs. All damage tests (xwOBA and squared-up) fail in both seasons. Bat speed hints in 2024 only; retest on 2026 data (pre-registered). They stay descriptive cards |
| Trait reliability | `traits_reliability.py` | Stable (split-half 0.99+, year over year 0.84 to 0.93), so failures are not noise |
| Field audit | `traits_fields.py` | Bat-tracking fields exist on 98 to 99% of missed swings (2025), so angle results are not selected on contact. Ball-bat intercept fields are not in the downloaded columns |
| Path generator | `paths.py`, `path_variants.py` | Value-versus-Contact nearly equal. "Decide every pitch" is +0.75 to +1.93 runs per 100 PA over Value for all 18 hitters in one game, but this is an in-sample upper bound and its extra calls are thin evidence. Policy iteration with the confidence rule did not help (-0.5 to +0.4). Hunt is 0.7 to 3.2 runs per 100 PA worse |
| Hitting plan vs the league | `docs/G1_EVIDENCE.md` | Count, confidence bounds and pitch shape drive calls; hitter-specific per-cell data adds little at these sample sizes (median 0.2 of his swings behind a cell) |

Known model limits: one calibration slope fails (swing value 1.086, a planned fix); plan silent on about half of pitches; no anticipation term; 2025 demo games are partly in-sample for the plane term (real validation needs 2026 data); the "± runs per 100 PA" ranges include only cell noise, not model error or selection bias.

## 5. Plan v5 status (from `/root/.claude/plans/proud-dancing-teapot.md`, summarized in `docs/ROADMAP.md`)

Done: field audit, trait reliability, plane fit with controls, traits re-test against the full kernel, squared-up outcome test, plane term adopted, plate-appearance DP, path generator v1, path report in the boards and viewer, model stamp and refresh, code review, research prompt.

Not done, in priority order:
1. **Close the intent-to-outcome loop** (the main finding of the code review): the saved coach choice is never used by the review; the log has no coach identity, model version, offered paths or outcome link; success is measured as agreement with the model, not development; nothing tracks a hitter across games. A design is proposed in `reports/Hitting approach intent and success.md` (a research-note synthesis; its claims are search-snippet level and unverified).
2. Coach session on the path picker and thresholds; the 20-minute interview questions are in that report.
3. Anticipation test and sequencing model (decides whether Hunt ships).
4. One-page pregame sheet per hitter; review against the chosen path; hitter goal records.
5. 2026 data refresh and rerun of the bat-speed damage test; swing-slope calibration fix.
6. Code-review fixes: HTML escaping in the viewer, Origin check and size cap on write endpoints, move research helpers out of the serving path (`plane_term` imports `traits_test`), rename `mockup.py` to `engine.py`, tests for `paths`, `plane_term`, `opportunity`, register path thresholds.
7. TrackMan or Hawk-Eye onboarding with a field audit; org approval; coach training; trial setup.
8. Design and copy pass (task 11) with the owner's feedback.
9. First run of the Mac launcher and native window (untested; cannot be tested from the cloud).

## 6. How to run and verify

- Setup: `pip install -e '.[dev]'` (desktop extra for the window).
- Server: `PYTHONPATH=src python3 -m gameplan.server --league data/league --app-dir data/app --port 8765`.
- Tests: `PYTHONPATH=src python3 -m pytest -q tests --ignore=tests/test_viewer_smoke.py` (88 tests, about 50 seconds). The browser click-through (`tests/test_viewer_smoke.py`) takes about 9 minutes. One library-open test (`tests/test_server.py`) is intermittent: a timing race in the viewer, not related to the model.
- Rebuild after any model change: `python -m gameplan.refresh ...` (about 25 minutes for four games, in two waves).
- Design: the project uses the Impeccable skill and hook; the viewer has no findings. Look: white background, vintage Diamondbacks purple `#5F249F`, teal `#005F61`, copper `#8F654D`, JetBrains Mono throughout.

## 7. Environment facts that bite

- The cloud session's outbound network is allow-listed. Page reads for mlb.com, PubMed Central, JMIR, FanGraphs, SABR and others were blocked, which is why the research is thin. The owner can add domains under the environment's network settings.
- Background jobs are killed when the session sits idle; always rerun `refresh` (it resumes).
- Data: `data/league` is the full 2025 season (with team columns); `data/b3` and `data/b24` are per-hitter samples used by the tests; `data/app/games/<pk>/` holds built games. Built games are currently out of date after the last stamp change and will rebuild on the next refresh.
- Do not run `pkill -f` on patterns that match your own shell.

## 8. Where to read next

`docs/ROADMAP.md` (shipped and next), `docs/CODE_REVIEW.md` (ranked findings), `docs/RESEARCH_PROMPT_v2.md` (research agenda and the owner's answers), `reports/Hitting approach intent and success.md` (unverified synthesis), `docs/scorecard.md`, `docs/traits_test_v3.txt`, `docs/plane_fit.txt`, `docs/paths_evidence.txt`, `docs/G1_EVIDENCE.md`, `docs/COACH_WALKTHROUGH.md`, `PRODUCT.md` (voice and visual direction). `README.md` still describes the earliest core (v0.3) and is out of date.

## 9. Update, 2026-10-04 evening

- **New direction:** `docs/GAMEPLAN_V2_PLAN.md` (owner's V2: one video loop that trains pitch recognition and drives the plan). Locked: two calls per hitter by pitch shape and zone, locked pregame, automatic receipt (execution only), no Hunt, no hitter leaderboard. Open: whether recognition is the Visalia problem, video feasibility (Gate V), org approval. The existing app is on hold until the plan is settled; nothing was removed.
- **Gate 0 on public MLB data** (pre-registered in `docs/GATE0_PREREGISTRATION.md`, results in `docs/GATE0_READOUT.md` and `docs/gate0_results_*.txt`, code `src/gameplan/recognition_paths.py`): two focus pitches come up 2 to 4 times a game on coarse shapes and the flagged pitches cost 25 to 50% more than his others, but they hold only about a third of his mistakes; the personal edge over a starter-level ranking is small; the "looks like his fastball" weighting is not supported once pitches are matched on where they end up. Recommended working definition: pitch type by height in his zone.
- **Data correction:** the earlier "MiLB" feasibility numbers were MLB data (the `bulk --minors` pull returned MLB games). `--minors` is now disabled. No real minor-league sample has been tested; the owner will upload one later.
- **Evidence ledger:** `docs/V2_EVIDENCE.md`. Six of the V2 plan's evidence rows have no source in this repository; none of its 18 claims is verified here.
- **Still no coach-facing change since the pivot:** the code review findings (HTML escaping, write-endpoint checks, intent-to-outcome loop) are open.
