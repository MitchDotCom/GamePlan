# Recognition tracking in the go/no-go game, 2026-10-08

## What it does
Every decision in the page is logged with who made it and what the pitch really was. The log downloads as one CSV (`gonogo_trials.csv`), and `python -m gameplan.recognition_profile --trials <csv> --out <dir>` turns it into one profile per player (JSON and an HTML page) plus a team summary.

On the page: a player field (required), Training mode (feedback after each pitch) or Assessment mode (no feedback shown and the reveal clip does not play), a "Run block" button (all pitches in random order, seeded by player and session), and the download button. Trials are kept in the browser's local storage on that device and survive a reload, but are not shared between devices: export from each tablet and pass all files to the profile command.

Each trial row: player, session, mode, time, clip, task (zone = strike or ball, pitch = which pitch), pause in ms, the choices offered (`options`), call (Strike, Ball, or the pitch type code), decision time, the answer key, correct or not, and the pitch's pitch type, family, pocket, plate location, zone top and bottom, speed, batter side, pitcher hand, release frame. Pitches without a key are logged and timed but not scored.

## What the profile reports, per player and per task
- Accuracy with a 95% interval, next to the accuracy of always giving the better single answer (so a 60% means something different on a 50/50 test and a 70/30 test).
- Strike or ball: d' (how well he separates strikes from balls) and criterion (leans Strike or Ball). These do not depend on how strike-happy he is, and they allow comparison across tests of different difficulty.
- Which pitch: he picks from that pitcher's own pitch types, so there is no d'. Accuracy is shown next to the chance level for the number of choices offered and next to always naming the most-thrown type, with recall per thrown type and a list of what he named instead (`confusions`).
- By pocket (a 3x3 grid as the batter sees it), pitch family, pitch type, and distance from the zone edge, each with a count and interval. A cell with fewer than 8 trials is shown as "too few", not as a number.
- A list of cells whose whole interval sits below his own average ("places to look at on video"). With many cells some appear by chance, so the page says it is a review list, not a diagnosis.
- Decision time overall, for correct and for wrong answers; session by session trend.
- `compare()`: change in d' between two sessions with a bootstrap interval, refused below 30 scored trials in either session.

## How it relates to the Rangers/uHIT report
Same structure: a fixed set of pitches, zone recognition and pitch-type recognition scored separately, repeated over time, reviewed one-on-one. The report is a vendor-coauthored case report (ledger row 13, grade C), so its figures (67% zone, 53% pitch type at baseline over 120 pitches) are context, not a standard. d' is used here because plain accuracy depends on how the test is built.

## Tested
- `tests/test_recognition_profile.py` (5 tests): d' with no infinities, recovery of a planted weak pocket (only that pocket is flagged), small cells hidden, session comparison detects a planted improvement and refuses thin sessions, HTML and edge buckets.
- Browser run (headless Chromium, three real low-home clips with synthetic answer keys): player required, assessment block ran all three pitches in a seeded order, no feedback shown, trials logged with pitch characteristics, training-mode feedback shown, CSV downloaded and read by the profile command.

## Not done
- No assessment form yet: the 120-pitch fixed forms (A and B), balanced by pitch type, pocket, pitcher hand and difficulty, need a clip pool that does not exist. The page runs whatever pitches it is built with.
- No test-retest reliability of the measures (needs real players, two weeks apart; see `docs/V8_PILOT_PROTOCOL.md`).
- Storage is per-device. Names are stored as typed; use IDs and keep the files inside org systems.
- Zone key is the ball's position, not the umpire's call; with TrackMan the default zone is used unless heights are supplied.
- The profile has not been run on any real player's trials.
