# Low-home video proof of concept (Visalia footage), 2026-10-07

Code: `src/gameplan/lowhome_release.py`. Footage: three Visalia low-home clips supplied by the owner. They stay out of the repository (scratch folder only).

## The footage

1280x720, 59.94 fps, H.264 plus AAC audio, 8.5 to 9.5 s per clip, no timecode stream. Fixed camera behind home plate in the stands, shooting through the net. The pitcher is about 165 pixels tall. Each clip is one pitch: about 6 s of waiting, the delivery, the follow-through, and the pitch arriving.

## Release without audio

Owner's constraints: Visalia video has no clock to match to tracking, and audio volume is unreliable. The detector uses neither.

1. **Delivery window:** the strongest 1.2 s burst of motion in a box around the pitcher.
2. **Ball track:** small, bright, neutral-colored blobs that are not at the same place a few frames earlier or later (so not static: lines, shoes, plate). Linked frame to frame into a track that falls at a steady 3.5 to 14 px per frame in a narrow column, bridging up to 5 frames the net hides. A track must start within 0.15 s before to 0.30 s after the motion peak.
3. **Release** = first frame of that track, which is also the top of the ball's path before it falls.

Audio was checked and, as the owner said, it is not safe to use: in clip 3 the loudest sound is at 9.08 s, but the sound that fits the delivery is at 8.59 s or 7.49 s.

## Result against hand labels

I labeled the first frame where the ball is clearly separate from the hand, by eye at 1-frame steps, before running the finished detector on clips 2 and 3.

| Clip | Hand label (frame) | Detector (frame) | Difference |
|---|---|---|---|
| a1016406-2443D | 456 (7.608 s) | 456 | 0 |
| ca219ed8-2444D | 396 (6.607 s) | 396 | 0 |
| cffae42a-2439D | 418 (6.974 s) | 418 | 0 |

**What this does not show.** I tuned the thresholds, box and window on these same three clips (the first version missed two of them because of net gaps and a wrong later track). That is a fit, not a test. For clip 3 the ball was at the fingertips one frame earlier, so its label could be 417. Held-out clips are needed.

## What the hitter would see

On this camera the ball travels toward the lens, so it passes in front of the pitcher's body.
- 50 ms after release: ball clearly visible (about 10 px, white).
- 100 ms after release: faint.
- 150 ms after release: not visible in any of the three clips. Only the follow-through is on screen.
- The ball is trackable for only 6 to 8 frames in total.

So on this camera a pause 150 ms after release shows no ball. For a pitch-recognition game the pause point would have to be about 50 to 100 ms, or the stimulus has to include something other than the ball (release point, arm slot, delivery). This was not tested with hitters.

## Package (one command per clip)

`cut_package()` writes a pre file (1.6 s lead-in to release + offset, no audio) and a reveal file (from the pause on), with the release source recorded as "video (ball track)". Default offset 150 ms; see the visibility finding before using it. No answer key is produced here because these clips have no tracking data attached (the owner said the TrackMan export is not needed yet).

## Still unknown

1. Accuracy on clips the detector has not seen. Needs 10 to 20 more low-home clips (different pitchers, left- and right-handed, lighting, parks, innings). I would label them by eye first, then run the detector blind.
2. Whether the pitcher box and ball corridor hold when the camera is zoomed or moved (they are fixed pixel boxes for this camera position).
3. Whether the ball track survives glare and busier backgrounds.
4. Which pause offset trains recognition. Needs the pilot.

## Update: profile-based detector and playable go/no-go page

- Detector now uses a camera profile (`config/lowhome_profiles/visalia_low_home_dev.json`) learned by `lowhome_batch calibrate`. On this camera calibration needed one rough hint point on the pitcher (`--near x,y`) because a fixed object falls at the same place in every clip. Without the hint it refuses rather than guess.
- On the three development clips it reproduces the hand-labelled release frames exactly (456, 396, 418). These clips were also used to tune it, so this is not a test. The held-out acceptance test in `LOWHOME_ACCEPTANCE.md` (30 or more clips, two labelers) is still to do.
- `lowhome_demo` builds one self-contained HTML page (go/no-go). Browser check (headless Chromium, 3 pitches x pause 100 ms and 50 ms): the video paused 1.7 ms (0.1 frame) after the target every time; buttons appeared, decision time logged, reveal played, no page errors.
- Answer keys are not set. They need TrackMan rows for these pitches; the page shows "no key" until entered.
- The ball fades from view by about 100 to 150 ms after release on this camera, so 50 to 100 ms pauses are the useful range.
