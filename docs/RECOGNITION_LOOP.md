# The recognition loop: upcoming starter, to hitters, to the season ledger

Written 2026-10-09. What exists, how to run it, what each check guards, and what is not proven.

## The loop

```
schedule ──> next_starter ──> prepare ──> hitters answer ──> season_ledger ──> coach board
 (who?)      (confirmed or    (build +     (phone app,        (per hitter, per
              tbd, never       gates,       Strike or Ball,    camera type, with
              guessed)         fail closed) then which pitch)  n and intervals)
```

1. **Who.** `python -m gameplan.next_starter --team 109 --on 2026-04-10` reads the schedule for our next unfinished game and the opponent's probable pitcher. Status is `confirmed`, `tbd` (game exists, no pitcher listed) or `no_game`. A probable pitcher can change, so the result carries `checked_at`: ask again on game day.
2. **Prepare.** `python -m gameplan.prepare --team 109 --on 2026-04-10 --work W --content C [--sim]` resolves the starter, pools his last four starts, builds per batting side a **next-starter pack** (his most-used pitches, the validated rule), an **Edges pack** (his pitches within 3 in of the zone edge, half in and half out), **random packs** from his team, and an **assessment pack** (answers withheld from the phone). Then it runs the gates below and writes `W/prep_report.json`. Exit code 0 only when nothing FAILED. `--pitcher-id N` is a manual override and is recorded as a warning.
3. **Hitters answer.** The phone app asks Strike or Ball, then which of that pitcher's own pitch types. Every answer is logged with player, session, mode, pack, clip, pause, choices offered, camera, decision time, key and correct.
4. **Ledger.** `python -m gameplan.season_ledger --trials <csv or trials.jsonl ...> --out <dir>` writes `leaderboard.html`, `.csv` and `.json`, plus a full per-hitter ledger in the JSON.

`--sim` draws each pitch from its tracking instead of cutting a clip (see "Drawn pitches"). No video is fetched in that mode, so it works for any game with tracking, including Triple-A and the Florida State League, where no clips exist.

## Gates in `prepare` (fail closed)

| Gate | Fails when |
|---|---|
| starter_confirmed | the schedule has no probable pitcher (build is refused); manual override is a warning |
| history | no earlier starts found (FAIL); fewer than 3 starts or 100 pitches (WARN) |
| playable_clips | the next-starter pack has fewer than 6 items per side |
| clip_files | a clip is missing, under 10 KB or over 3 MB, runs less than 0.4 s past release, or release is outside 0.3 to 3.0 s |
| sim_geometry | (`--sim`) a drawn path's end point disagrees with its strike key or its result-card location |
| no_repeats | the same pitch appears in two packs of one queue (a training repeat of an assessment pitch hands the hitter the answer; found in the first real-clip build, where one pitch was in both a random and the assessment pack) |
| answer_keys | a training item has no strike key or pitch type; an assessment item carries a key; an assessment key is missing from the private file |
| choices | a pitcher with one pitch type in the sample is never asked (the builder skips him); an item offers fewer than 2 or more than 7 pitch types, duplicates, or leaves out the thrown type |
| edges | the Edges pack has no strikes or no balls (WARN if fewer than 6 clips or lopsided) |
| coverage | the starter pack is all strikes or all balls (WARN); location spread is narrow by design (usage picks where he throws most), which is why the Edges pack exists |
| usage_fit | a starter-pack pitch is outside his top usage shapes to that side |

Each gate has a test that feeds it the specific failure (`tests/test_prepare.py`). On the cached Singer data (game before 2025-06-11) every gate passes except the coverage warning: his usage pitches to right-handed hitters sit in one pocket (low-away), which is what the Edges pack addresses.

## Drawn pitches (`simview.py`, phone app canvas)

A pitch is drawn from the nine tracking parameters (release point, velocity, acceleration) with p(t) = p0 + v0 t + a t²/2. A row becomes a drawn pitch only if all of these hold: fields present and finite; release plane near 50 ft; zone time 0.30 to 0.60 s and equal to the feed's `plateTimeSZDepth` within 5 ms; the path reproduces the feed's plate location within 0.02 ft; speed from the vector within 1.5 mph of reported; the ball moves toward the plate throughout. Each gate has a test that corrupts a real row to trip it. On 1,127 cached pitches all pass.

Two views: **hitter's eye** (camera at the batter's eye on his side of the plate, pause up to 250 ms) and **low behind home** (camera behind the plate; pause up to 300 ms). The recap after the answers is always from behind the plate, with the field of view widened per pitch until the zone, the crossing and the whole path fit. Tested:

- projection maths (centre, +x right, +z up, size falls with distance, points behind the camera refused);
- the ball is drawn at the pause where the maths puts it, within 1 device pixel; the future path, zone and crossing marker are not on screen before the answer;
- the crossing marker lands on the tracked location within 1.5 device pixels;
- every shipped pitch, both views, every allowed pause, two phone widths: the ball stays inside the picture from release to the pause; the recap frames zone, crossing and path;
- a stalled picture (a frame gap over 250 ms) aborts the pitch with a message instead of jumping to the pause;
- same pitch, same offset, same view gives identical pixels; answers log `sim:<view>`; a pitch that would leave the hitter's-eye picture is shown from low-home and logged that way.

**What it is not.** A drawn ball has no delivery, arm slot, spin or lighting. It cannot train anything that depends on those. Whether it trains recognition at all is untested, and whether it transfers to real video is untested. The numbers match the feed's own fields, which is a consistency check on my maths and signs, not evidence about the physical world. Camera positions are approximate and not matched to any real camera (including Visalia's). The two views are not comparable with each other or with broadcast clips, so they are separate boards.

## Video angle

MLB clips are the home broadcast feed only (`feedType = 'HOME'`). Savant ignores every feed or camera parameter tried, and the Stats API content listing holds edited highlights, not per-pitch alternate angles. There is no public low-home or pitcher-front video per pitch. Low-home footage exists only from Visalia and needs org approval and a TrackMan join. Every clip and every answer carries a `camera` field so results are never compared across angles.

## The ledger and leaderboard (`season_ledger.py`)

Rules built in:
- Only **assessment** answers are ranked by default (training packs differ in difficulty and give feedback). `--mode train` ranks training answers and labels the board.
- **One board per camera class.** Broadcast video, hitter's-eye drawing and behind-home drawing never mix.
- A hitter needs **30 scored answers** on a metric to be ranked; below that he is listed, unranked. Every number carries n and a 95% Wilson interval.
- `reading` compares a hitter's interval with the group's pooled accuracy: above, below, or not distinguishable. At these sample sizes most hitters will be not distinguishable and the board says so.
- `vs peers` is accuracy minus what the other hitters scored on the same pitch and question (needs 4 others on that pitch), so a hitter who got easy pitches is not credited. This needs every hitter to see the same assessment form, which is how the assessment pack is built.
- Per hitter: strike/ball (accuracy, d', criterion), edge pitches, pitch type (accuracy against the chance level for the choices offered, recall by thrown type, what he named instead), decision time, the nine location pockets, and a monthly trend.

Tests plant known skill and known traps (`tests/test_season_ledger.py`): ranking order and tiers, thin hitters unranked, training excluded, cameras separated, an easy-pitches-only hitter whose raw accuracy flatters him but whose vs-peers is about zero, edge and chance baselines, monthly trend, duplicate rows loaded once.

## Not proven, in order of how much it matters

1. **Nobody has used it.** No hitter has answered a pitch in this app. The ledger has only been run on synthetic data.
2. **Recognition on this test says nothing yet about game performance.** No link has been tested.
3. **Drawn pitches** (above): perceptual validity and transfer untested. At 100 ms the mean positions of Singer's pitch types differ by 0.3 to 1.7 ft in 3-D, but much of that is speed (distance travelled), a weak depth cue; the image-space separation a hitter would actually see has not been measured. Pitch type from trajectory alone may be hard at short pauses.
4. **The next-starter resolver** has run only against recorded schedule structure and the API's field layout on finished games; there are no upcoming games to test against right now. Probable pitchers change.
5. **Release timing.** The video path infers release from the arrival sound minus the feed's `plateTime`, but the feed's zone-plane time is `plateTimeSZDepth`, about 32 ms shorter. Which one matches the glove sound has not been checked; the possible error on the pause point is up to about 30 ms.
6. **Leaderboard comparability** needs the same assessment form for every hitter and repeated forms across the year with enough answers (30 per metric is a floor for ranking, not for precision).
7. **Visalia.** No TrackMan or low-home content is wired into the builder; org approval is required first.
8. **Real iPhone.** All browser QA is emulated (Chromium, and WebKit as a stand-in for Safari).
