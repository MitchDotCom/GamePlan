# GamePlan v2: one video loop that trains pitch recognition and drives the game plan

Written 2026-10-04. Owner: Mitch (Player Development Associate, Arizona Diamondbacks, Visalia Rawhide). Status: working hypothesis, nothing adopted. This document supersedes `GAMEPLAN_V2_HANDOFF.md` where they differ and is meant to be read with `docs/HANDOFF.md` and `docs/RESEARCH_PROMPT_v2.md` in the repo.

## 1. Thesis

Hitters at Visalia already watch the starter's video the night before. That video is the best asset in the building and today it is passive: they watch, nobody checks what they saw, and the game plan is set once and never revisited.

GamePlan v2 turns that same video into a loop:

1. The engine picks each hitter's two calls (one take, one attack) from his own data and tonight's starter.
2. The same two calls choose the video clips he trains on that night, cut early so he has to recognize the pitch before seeing the answer.
3. The game plan he walks in with is the output of what he practiced.
4. A receipt the next morning shows how he executed those calls, and his recognition scores show whether he could see the pitches.
5. The next night's calls and clips are chosen from both.

One ranking drives both the plan and the training. That is the product. It is not a dashboard, a second scouting report, or a video library.

What this is not: a way to prove recognition training raises batting outcomes in one season. Section 6 says what can and cannot be shown.

### Decision status (read this first)

The owner has not yet said "build this". The first job in the build session is to run the tests that decide it, not to build.

Locked by the owner:
- Recognition is the north star and game planning is the way in.
- Per hitter, about two calls, defined by pitch shape and zone, locked pregame, with a cue.
- Plan made once pregame. Not per series, not in game.
- Automatic same-night receipt in the existing morning data email; next plan opens with it (carry, drop, adjust).
- Hitter message separates execution from results.
- No manual coach work. Hunt is out. No leaderboard visible to hitters; a board visible to staff and coaches only is acceptable.
- Video can be exported from TruMedia. Nothing needs to be proven with the org before the engine is proven.

Working hypothesis (answered by me as the owner's proxy, to be picked apart):
- One ranking drives both calls and the training clips.
- Calls are in the hitter's own zone and two is the starting number (Kill test C checks it).
- Receipt reports execution only.
- Raise TruMedia API access with the org after Gate 1.

Open, decided by results:
- Whether two calls touch enough pitches (Kill test A) and hold up (Kill test B).
- Whether the tunneling measure is real (Phase 1 proof of concept).
- Whether CSV-to-video alignment and release-frame detection work on real exports (Gate V).
- Whether hitters will do an 8 to 10 minute drill (pilot).
- Whether recognition is the problem for Visalia hitters (the first clip test).

## 2. Why this route (and what was rejected)

Four routes were compared on evidence, use of video, measurability, and effort. Full evidence is in section 11.

| Route | Verdict | Reason |
|---|---|---|
| A. Cue-action card plus game receipt | Keep, as the spine of planning and measurement | Cheap, automatic, only route that measures game behavior. No evidence it improves recognition by itself. |
| B. Video recognition training on the starter | Keep, as the training layer | Best-supported mechanism (occlusion training, specific-opponent training). Needs clips and enough dose. |
| C. Post-game review of own decisions on video | Later | Thin evidence for perception feedback. Becomes cheap once the receipt can name the pitches. |
| D. Pitcher tells and scouting cues | Not in the engine | Perishable, not measurable from tracking data, no evidence that teaching tells improves outcomes. Coaches can still add a free-text cue. |

The combination works because each half covers the other's blind spot. The receipt cannot tell "did not recognize it" from "recognized it and swung anyway". The clip test can, because it measures recognition directly, outside the game, on real video.

## 3. The system

### 3.1 One ranking drives everything

For each hitter and tonight's starter, the engine ranks pitch-shape-and-zone cells by value at stake:

value at stake = how often the starter throws the cell x how much the right decision is worth for this hitter (existing swing-versus-take model, per hitter lane) x how often the hitter gets it wrong.

"Gets it wrong" starts as a game-data proxy: his chase or take rate on that shape and zone compared with the better decision. Once the clip test has data, it is replaced by his measured recognition error on that shape, with the game proxy as a fallback.

The top take cell and top attack cell become the two calls. The same cells decide which clips he trains on. Calls are defined by pitch shape and zone, in the hitter's own zone (for example "top third of your zone"), never by count.

### 3.2 The clip set (tonight's drill)

Spec generated by the engine, 8 to 12 clips per hitter per night:
- Cue clips for the take call and the attack call, from the starter's recent starts.
- Look-alike clips: pitches that start on the same early path but should get a different decision. Recognition is discrimination, so a drill with only the cue pitch trains guessing.
- Fallback when the starter lacks enough clips in a cell: clips of the same pitch shape from other pitchers, flagged "generic" with lower confidence. The tennis result favors specific opponents, so generic is a fallback, not the plan.

### 3.3 The drill (8 to 10 minutes, phone or iPad, anytime that day)

- Clip plays from release, stops at a cut point, hitter answers with swing/take and zone (taps, not speech; players disliked calling pitches aloud in Fadde's program), then the clip continues to show the answer and full flight.
- Cut point starts late (about 200 ms after release) and moves earlier (150, then 100) as his accuracy on that shape rises. Adaptive difficulty is part of why the VR trial's adaptive arm beat the others.
- Camera angle: use the closest first-person-like angle available (low home) over CF when both exist. The team-sport meta-analysis favored first-person presentation.
- It replaces the passive playlist watch, not adds to it. Same time slot, same video, now with a question.
- Scores are per pitch shape, visible to the hitter, the hitting coach and staff. No leaderboard visible to hitters (owner's decision); a staff-only team view is allowed. Rewards are not part of the first version.

### 3.3b What the hitter app is

A small web page (no install) that plays clips with a stop frame, takes two taps, reveals, and logs to a file. It is the "separate app or layer on the nightly video" the owner described. Pitchbase and TruMedia are the video sources, not the drill surface, because they cannot stop a clip and ask a question.

### 3.3c Video source facts and the alignment rule

Facts from the owner (2026-10-04):
- TruMedia exports a starter's start as one continuous mp4, about 15 minutes for 50 to 100 pitches (roughly 10 seconds a pitch, 60 fps). There are visible cuts: a clip ends and the next clip is the next pitch.
- A CSV of pitch locations and tracking data can be exported for the same start. Overlays (pitch type, count) can be burned into the video.
- The mp4 usually matches the CSV, but some pitches have no video, so order alone is not a safe match.
- Angles used today for the night-before video: CF, open side, low home.

Rules that follow:
- Never show a hitter a clip whose label is uncertain. A wrong "answer" teaches the wrong thing and destroys trust. Uncertain means dropped.
- Alignment is checked, not assumed: read the burned-in overlay text (pitch type, count) from each clip and compare it with the CSV row. Use an overlay copy only for this check; the drill uses a clean copy so the overlay does not give away the answer.
- The splitter outputs an index (pitch ID, start, release, end), not new files, so the app seeks into the original. Hitters never hold a copy of the org's video.
- Pick the angle closest to first-person (low home) for the drill when available.
- Hosting the app and video where hitters can reach them needs org approval. Not a technical question; ask after Gate 1.
- Release frame: 200 ms after release is about 12 frames. Start with the 200 ms cut. Plate arrival minus flight time from tracking is a cross-check if plate arrival is detectable.

### 3.4 Game plan and meeting

The pre-game card for each hitter is one page: two calls, the cue words for each, his drill accuracy on those shapes, and last night's receipt with the carry/drop/adjust question. The hitting coach sees the lineup's cards and may change a call before it locks (one tap). The default is the engine's calls. A change after lock is logged as a change.

The 5 to 15 minute hitters meeting becomes a conversation about two calls per hitter, not a general scouting read.

### 3.5 Receipt (automatic, next morning, in the existing data email)

Per call: pitches of that shape and zone seen, swings, contact quality on those swings, plus the rolling total over recent games. Tallies, never a grade. It reports execution only and says so. It does not claim recognition.

Plain message to the hitter, in Mitch's voice: execution first, results second. 0-4 with a clean take on the bad pitch is a good night.

### 3.6 Carry-forward and call lifecycle

Each call is set, tracked over a rolling window, then graduated (stable), dropped (rarely shows up or does not matter), or adjusted. The next card opens with the receipt and one question per call. Hitters change over a season, so turnover is expected.

## 4. Nightly rhythm

| When | What happens | Manual work |
|---|---|---|
| Afternoon before the start | Engine reads tomorrow's probable starter and each hitter's lanes, ranks cells, picks calls, builds the clip spec | None |
| Evening before | Hitter gets a link, does the 8 to 10 minute drill any time | Hitter only |
| Pregame meeting | Coach reviews lineup cards, changes a call if needed | One tap per change |
| Game | Nothing | None |
| Same night or morning | Receipt generated from tracking data, added to the morning email | None |
| Next afternoon | Next calls and clips use the receipt and the drill scores | None |

Mitch's nightly work target is zero, with one weekly review of what the engine did. Anything that needs a person to build per-hitter playlists each night fails the owner's test ("too complex and manual").

## 5. Engine specification

Reuse from the existing repo: Statcast loaders, the swing-versus-take model, zone geometry, the hitter-versus-arsenal damage table, the pre-registered test method, the build and refresh machinery.

New modules:
- `lanes`: per hitter damage and chase by pitch family and zone, shrunk toward the league.
- `calls`: value-at-stake ranking, picks one take and one attack call, outputs cue words.
- `clipspec`: turns calls into a clip list with game and pitch numbers, look-alikes, and a generic fallback. Each pitch keeps its game and pitch number so TruMedia or Pitchbase can look up the clip later.
- `receipt`: conditional swing rates on each call from the tracking data.
- `lifecycle`: set, track, graduate, drop, adjust.
- `disguise` (only if Phase 1 passes): early-flight separation of each secondary pitch from the pitcher's own fastball, used to choose the cut point and to rank hard-to-recognize pitches.
- `drill_log`: stores answers and cut points from the hitter app.

Interfaces, so the video source can change without rewrites: the engine outputs a clip spec as data. A separate adapter turns it into a Pitchbase playlist, a TruMedia query, or files for the hitter app.

## 6. Measurement: what success is and what can be shown

Three layers.

| Layer | Metric | Source | Judged over |
|---|---|---|---|
| Recognition | Accuracy by pitch shape at a fixed cut point (for example 150 ms), per hitter, against his own baseline | Drill log | At least 4 weeks (meta-analysis moderator) |
| Execution | Conditional rate: swings at cue pitches seen, per call | Tracking data | Rolling window of games, not one night |
| Development | Chase rate and zone swing quality on the call cells | Tracking data | A season, versus his own prior |

Adoption metrics (drill completion, calls changed by coaches, hitters who read the receipt) are tracked separately because they predict whether anything else matters. Fadde's program is the reference: 14 of 18 used a voluntary tool.

What can be shown: whether recognition accuracy moves for hitters who do the drill, whether it predicts game behavior (the clip score versus the conditional swing rate), and whether execution on the call cells improves against each hitter's own baseline. Use a staggered start across hitters so some serve as a comparison before they begin.

What cannot be shown in one season: that recognition training raises overall batting results. A hitter sees roughly 15 pitches a game. If a call touches 2 to 4 pitches a game (Kill test A will give the real number), a 4-week window gives about 50 to 100 cue pitches per hitter. At that size a single hitter's rate has a standard error of roughly 6 points, so only large changes show up for one hitter. Pool across hitters and judge trends. This is my arithmetic, not a power study.

Thresholds for "working" are CHOICE values to be pre-registered before any hitter uses it. Do not set them after seeing results.

## 7. Stage gates

Each gate can stop the project. Nothing is adopted into the model until the owner has seen the results table.

**Gate 0: data only, no org approval needed**
- Kill test A (coverage): how many pitches does a take or attack call touch per game and per month? If under about 2 per game and 30 per month, widen the call or stop.
- Kill test B (stability): does a hitter's lane hold from the first half to the second half? If not, per-hitter calls are noise.
- Kill test C (concentration): do the top two calls carry most of the plan's run value? If not, two is the wrong number.
- Tunneling proof of concept on 2025 Statcast, confirmed on 2024, then public Triple-A and Florida State League data. The bar is written to `docs/` before running: held-out log-loss improves with the separation measure after controlling for location, velocity, movement, count, pitcher and hitter. If it fails, cues are plain and the engine does not use disguise scores.
- Needs baseballsavant.mlb.com in the environment network settings.

**Gate V: video feasibility (runs in parallel with Gate 0; owner supplies the exports)**
This is the make-or-break dependency for the recognition half. If it fails, version 1 ships the card and receipt with cue words and the existing playlist, and says plainly that recognition is not measured.

Inputs: 3 starts from different starters, ideally across parks, each as an mp4 plus the matching CSV, with and without overlay. Test the 200 ms cut only.

| Check | What it tests | Pass bar (CHOICE, fixed before looking) |
|---|---|---|
| Cuts found | Detected clip count versus clips actually present | Matches the owner's hand count on all 3 starts |
| Alignment | Overlay text versus CSV rows, including pitches with no video | At least 90% of pitches matched, and 0 mismatches shown |
| Release frame | Detected release versus a hand-marked frame on 20 clips | Within 3 frames on at least 80% |
| Usable set | Clips left after drops, per hitter's two calls | Enough for 8 to 12 clips a night (depends on Kill test A) |

If release detection cannot reach 3 frames, the 100 ms cut stays off and the drill starts at 200 ms. If the file is too large to hand over, the build session writes a script the owner runs locally that prints the four numbers.

**Gate 1: retro-simulation on real data**
Build cards and receipts for real 2025 hitters and starters, and open the next card from the receipt. Ten to twenty worked examples. Owner and a coach judge whether the calls make baseball sense. If they do not, fix the ranking before building anything for hitters.

**Gate 2: org approval and video access (owner-led)**
Needs: approval to use it with real hitters, access to starter video through TruMedia (the owner has not confirmed API or download rights), the club's tracking export fields, and which parks use TrackMan or Hawk-Eye. Compare only within one system.
Run a pilot with 3 to 5 hitters for 6 weeks: the hitter app, the receipt, and the card. Pre-registered metrics from section 6. Kill criteria: drill completion under a CHOICE threshold, or no relationship between clip accuracy and conditional swing rate.

**Gate 3: scale**
Roster, then other affiliates through TruMedia. Only if Gate 2 shows adoption and a measurable relationship.

## 8. Dependencies and asks

For the org (owner decides timing; raise after Gate 1 gives something to show):
- Approval to run a hitter-facing pilot.
- Video: TruMedia clip access and download or export rights for the hitter app. This is the biggest unknown.
- Tracking export: which fields (trajectory parameters, release, bat tracking) and which parks use which system.
- Whether MiLB follows the MLB rule banning in-game recommendations from dugout tablets. Low priority, since this plan is pregame.

For the owner before the cloud session:
- Add baseballsavant.mlb.com to the environment's network settings.

## 9. Risks and open questions

| Risk | Why it matters | Mitigation |
|---|---|---|
| Dose and adherence | The team-sport meta-analysis found programs over 4 weeks worked better and sessions under 10 minutes did not. Voluntary tools lose users. | 8 to 10 minute sessions in the slot hitters already use; measure completion from week one; kill criterion in Gate 2 |
| Clip supply | The starter may not have video in every case. Pitchbase only views and shares. | Generic fallback flagged lower confidence; clip spec is data, so the source can change |
| Small samples | Few cue pitches per hitter per game | Report tallies, judge over weeks, pool across hitters |
| Recognition versus decision | A game miss cannot separate the two | Clip test measures recognition separately |
| Tunneling is a conjecture | Evidence it changes hitter decisions is thin | Phase 1 gate; fall back to plain cues |
| Trust | "Why would they trust me and a model?" | Built from the hitter's own data; he sees his own clip results first; coach can change a call; calls and reasons are visible |
| Reward design | Gamification evidence in sport was not found | Open question; start with private scores, no leaderboard |

Open questions that only coaches can answer (20-minute interview): how an approach is said out loud today; what a coach would write down in five seconds; who besides the hitting coach should see the plan; what makes a hitter ignore a card; whether hitters would do an 8 to 10 minute drill at home or at the park.

## 10. Not doing

- Hunt (hidden, scored 0.7 to 3.2 runs per 100 PA worse than Value, execution cannot be checked).
- The three-path picker, "Decide every pitch", and the agreement-with-model score as the main surface.
- In-game dugout recommendations.
- Pitcher tells in the engine.
- Per-hitter hand-built playlists as the operating model.
- Trajekt-style machine plans (affiliates do not have them).
- Any use of confidential org data in the repo.

## 11. Evidence (tiered; items marked unverified were read from abstracts or secondhand summaries)

Tiers: A peer-reviewed or primary data, B documented practitioner account, C vendor or marketing, D opinion.

| Claim | Source | Tier | Note |
|---|---|---|---|
| Temporal occlusion training: large effect, no difference between video and field tests; 12 studies | Muller and Morris-Binelli meta-analysis (sponet.de/sponet/Record/4090091) | A | Bias analyses inconclusive |
| Perceptual-cognitive training in team sports: lab 1.51, game transfer 0.65; screens 0.19, life-size video 0.46, VR 0.96; verbal responses smaller; over 4 weeks better; sessions under 10 minutes ineffective | Behavioral Sciences 2024 (mdpi.com/2076-328x/14/10/919) | A | Half the studies had proper controls |
| Opponent-specific training improved accuracy only with the same opponent; 39 pro tennis players, 72 trials, about 1 hour | Frontiers in Psychology 2024 (fpsyg.2024.1508627) | A | Lab only, no match transfer test |
| VR batting RCT, 80 players, 6 weeks: better league stats and level reached | Frontiers in Psychology 2017 (fpsyg.2017.02183) | A | Abstract only, no effect sizes, one lab's system |
| Visual and oculomotor skills predicted 22 to 28% of swing discipline variance; 71 minor leaguers | bioRxiv 2020.01.21.913152 | A (preprint) | Exploratory |
| Single-A anticipation correlated with walk rate (r about .35, n=34) | Earlier research note | A | Not re-verified this session |
| If-then plans in sport: 11 studies, mixed; better with objective cues | Bieleke et al. scoping review | A | Underpowered studies |
| Process goals d=1.36, performance 0.44, outcome 0.09 | Goal-setting meta-analysis (earlier note) | A | Not re-verified |
| Progress monitoring d=0.40, larger when recorded and reported | Harkin 2016 (earlier note) | A | Not re-verified |
| Swings start within about 100 ms on largely 2D information | Baseball Prospectus, "Understanding swing processes" | B | Article, not a study |
| Skilled cricket batters use pre-release and pre-bounce cues better | Murdoch University occlusion study | A | Cricket, not baseball |
| 19 trackable pitcher tell markers | Baseball America, "Tipping Pitches" | B | No data |
| Minor leaguers at 53% pitch recognition on a go/no-go test; two OPS case studies | ABCA article on uHIT | C | Vendor, selection-biased |
| Augmented feedback in cricket: anticipation g=1.21, performance 0.55, neither significant | PLOS ONE review (ideas.repec.org/a/plo/pone00/0279121) | A | No isolated feedback arm |
| Closer early paths mean higher whiff rates (tunneling) | Roegele via Hardball Times | B/D | Secondhand, methods not seen |
| Fadde college program: 20 pitches in 5 minutes, voluntary, 14 of 18 used, players disliked calling pitches aloud | Earlier research note | B | Not re-verified |
| Batter-versus-pitcher history adds little beyond season stats | Earlier research note | A/B | Not re-verified |
| Hitters differ stably by pitch type (r about .7 year to year, MLB only) | Earlier research note | A/B | Needs Kill test B at Single-A |

Not verified: PubMed Central pages were blocked, GameSense and some other pages were blocked, TruMedia API terms, MiLB tablet rules, which Visalia park system and export fields.

## 12. Decisions needed from the owner

1. Approve the thesis in section 1: one ranking drives both the plan and the clip set.
2. Confirm the calls are defined by pitch shape and zone in the hitter's own zone, and that two is the starting number (Kill test C will check).
3. Confirm the receipt reports execution only.
4. Decide when to raise TruMedia access with the org (recommended: after Gate 1).
5. Resolved: no hitter-facing leaderboard; a staff and coaches only view is acceptable.

## 13. Working rules for the build session (carried over)

- Plain, brief, direct. No filler, flattery, preamble or closing summaries. Recommend first. No em dashes. Avoid "robust", "seamless", "certainly", "actually", "leverage", "comprehensive".
- Do not do more than asked. Deliver what was asked and stop.
- Nothing is adopted until the owner has seen the results table. Every number is fitted or sourced with a stated method; unfitted values are labelled CHOICE.
- Pre-register tests (held-out period plus a second-season confirmation) in `docs/` before running.
- If the owner calls something too complex or manual, treat it as a design failure and simplify.
- If something is vague, ask one or two plain-baseball questions, not jargon.
- Long jobs run in the background. Commit and push every change. Never open a pull request unless asked. Branch `claude/baseball-hitting-strategy-engine-iwo2dz`, repo `MitchDotCom/GamePlan`.
- GitHub GraphQL is blocked; use `gh api`.
- First actions in the new session: read `docs/HANDOFF.md`, `docs/RESEARCH_PROMPT_v2.md` and this file; run the Savant access check; if it passes, write the Gate 0 pre-registration into `docs/`, run the kill tests, show the three tables and stop. If access fails, tell the owner and stop.

Savant check: `curl -s -m 15 -o /dev/null -w "%{http_code}" "https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfSea=2025%7C&player_type=pitcher&game_date_gt=2025-06-01&game_date_lt=2025-06-01&type=details"`
