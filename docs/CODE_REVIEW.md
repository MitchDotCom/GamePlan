# Code review (2026-10-04)

Scope: the whole repository at commit after `Model stamp follows the build's real import chain`. 59 Python modules (about 10,000 lines), 17 test files (88 fast tests, plus a 9-minute browser click-through), a 250-line viewer. Method: import graph, test-to-module map, a read of the engine, server, review and viewer code, and a check of every claim in the docs against what the code does. Ranked by what matters for the stated goal: a tool coaches use, with intent captured and success measured.

## A. Product gaps that matter more than any bug

1. **Intent is captured but never used.** The coach's choice is saved per `date|starter|hitter|time-through-order|count` with `path`, `why`, `note` and a save time (`viewer.js` logView, `server.put_log`). The review layer (`game.py`, the `for pol in (OFF, CONTACT_FIRST)` loop) grades every pitch against the model's default plan or the contact-first policy. It never reads the path the coach picked. So the loop the product is supposed to close (plan, coach picks, hitter executes, review against the pick, outcome) stops after step two. Still missing from the saved record: who chose (no coach identity), which model version and paths were on screen (no stamp, no `plan_id`), the paths that were offered, a plate-appearance or game-level intent, and any link to what happened.
2. **Success is not defined inside the product.** The review labels (`FOLLOWED_PLAN`, `HITTER_BEAT_MODEL`, ...) measure agreement with the model. That is obedience, not development. There is no per-hitter trend across games, no goal a coach can set for a hitter, and no outcome tie-back. `success.py` and `pilot.py` hold the analysis design but nothing in the app stores or shows results over time.
3. **No coach-language intent.** Coaches describe approach in words ("sit on the heater away early", "take until strike, then spray"). The app offers model-derived paths and four log choices (Value, Contact, Decide every pitch, My own plan). "My own plan" captures nothing about what the plan was.
4. **Uncertainty is shown in a way that overstates.** "Decide every pitch" shows `+x ± y runs / 100 PA`. The gain is selected on the same estimates it is scored on (winner's curse) and the ± covers cell noise only. Coaches will read it as an expected gain. Needs a shrunk or held-out estimate before it is shown.
5. **Plan silence plus new thin-evidence calls.** The plan says nothing on about half of pitches; the new path calls most of them. How coaches treat a low-confidence recommendation is a research question, not a model question.

## B. Correctness and honesty risks

6. **Stamp coverage.** The first version of the model stamp used a hand-kept file list and missed modules the build imports. Fixed in this review: the list now follows the real import chain of `game.py`.
7. **Look-ahead in the 2025 demo games.** The plane-term coefficient and league curve were fitted on 2025 swings (curve before 2025-07-01, coefficient on swings after it). A demo game dated September 2025 is therefore partly in-sample for that term. Fine for a retrospective demo; not evidence of prospective performance. Real validation is the 2026 refresh.
8. **Duplicated constants.** `GO_DELTA`, `NO_GO_DELTA` live in `decision.py` as literals and in `constants.py` as registered values. A test could compare them, but nothing forces it. `paths.py` thresholds (`VIABLE_TOL`, `MIN_DIFF`) are not registered at all, and 9 registered constants are labelled CHOICE (not fitted).
9. **Public-data zone assumption.** The called-strike model assumes human umpires. If the Single-A park uses automated ball-strike calling, the take side of every call is wrong. Needs a fact check before any Visalia use (see the research prompt).

## C. Structure

10. **Research code sits in the serving path.** `plane_term` imports from `traits_test`, which imports `validate_mlb` and `study`. The build's import chain is 29 modules, 5 of them research scripts, so editing a study forces a rebuild and the shipped engine depends on test harnesses. Move the shared helpers (`_fit_logit`, `_vba_feats`, `_boot`) into one small module.
11. **Naming.** `mockup.py` and `mockup_html.py` are the production engine (`Engine`, `build_board`). New contributors will not look there.
12. **One package, two jobs.** 25 of 59 modules are one-off analyses whose outputs live in `docs/`. Fine for research velocity; they should move to `analysis/` before anyone else reads the repo.
13. **Test gaps.** Production modules with no test: `paths`, `plane_term`, `opportunity`, `mockup` (the engine), `game_html`, `preview`, `bulk`, `fatigue`, `success`. The DP has unit tests; the path rule and the plane term are covered only by a manual run. The browser test takes about 9 minutes, so it is skipped in practice.
14. **`game.build_game`** is about 200 lines mixing data loading, hitter fits, plate-appearance review and board setup. Works; hard to change safely.

## D. Viewer and server

15. **No HTML escaping.** The viewer builds pages with template strings and `innerHTML` and has no escape helper. Coach notes, hitter names from data, and the log export are inserted raw. A note containing markup runs in the page. Low risk on a single-user laptop; real once notes are shared or imported.
16. **Viewer maintainability.** `viewer.js` is about 250 lines with many lines of 500 to 900 characters. A product with a path picker, a log and a review will not survive further growth in this form.
17. **Server trust.** Bound to localhost (good). No Origin or Host check, so any page open in the coach's browser can send `POST /api/refresh`, `POST /api/build` or `PUT /api/log`. The log is one JSON file replaced whole on every save: no size limit, last writer wins across two tabs, and no per-coach identity.
18. **Packaged-app risk.** The stamp reads source files; in a packaged app those may be bytecode only. It then hashes whatever is present, which stays consistent within one release but is untested.

## E. What is solid

Pre-registered tests with held-out periods and second-season confirmation, and every result written to `docs/`. The geometry is tested against raw rows and umpire call rates. The plate-appearance DP reproduces the count table within 3.5%. Builds are staged and swapped in atomically, and a killed run resumes. The scorecard is honest about its one failure (swing slope) and one unmeasured item.

## F. Fix order (small, mine to do now unless you say otherwise)

1. Escape every inserted string in the viewer (one helper, applied to all inserts).
2. Origin check on the three write endpoints; cap the log body; per-save merge instead of replace.
3. Move shared helpers out of `traits_test`; rename `mockup` to `engine`.
4. Tests for `paths` (shown-path rule), `plane_term` (identity at zero coefficient), `opportunity`.
5. Register the path thresholds and read `GO_DELTA` from the registry.

None of these change a number a coach sees. The research below decides what to build on top.
