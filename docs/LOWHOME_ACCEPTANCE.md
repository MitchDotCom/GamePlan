# Low-home release detector: acceptance test (written 2026-10-07, before the held-out clips exist)

Purpose: decide, with numbers fixed in advance, whether the visual release detector is good enough to cut go/no-go clips with no manual step. The three clips supplied so far are development data and cannot count toward acceptance.

## Held-out set

- At least 30 low-home clips, none used for any tuning.
- At least 3 pitchers, left- and right-handed both present, at least 2 different lighting conditions, at least 2 ballparks or camera positions.
- Each clip is one pitch with the pitch arriving inside the clip.

## Labels

- Definition (fixed): release frame = the first frame where the ball is clearly separate from the pitcher's hand, read at 1-frame steps. Where the previous frame shows the ball at the fingertips, the earlier frame is not used.
- Two independent labelers (Claude and the owner, or a second staff member). Labels are made before the detector is run on the set.
- A clip where the two labels differ by more than 1 frame is "ambiguous". It is reported separately and excluded from the accuracy rates, but counted in the totals.

## Metrics and bars

| Metric | Bar |
|---|---|
| Share of clips within 1 frame of the labels (both labelers) | at least 90% |
| Share within 2 frames | at least 97% |
| Mean signed error (detector minus label) | within +/- 0.5 frame |
| Clips with no release found (fail closed, no package made) | at most 10% |
| Clips with a release found but off by more than 3 frames (silent errors) | at most 2% |
| Ambiguous clips | reported, no bar |

The silent-error bar is the one that matters most: a clip that is skipped costs nothing, a wrong cut trains on the wrong moment.

## Required behavior (checked in tests, not by eye)

1. **Fail closed.** If any internal check fails (no delivery found, no ball track, track not plausible, track disagrees with the delivery timing), no package is written and the reason is logged.
2. **No per-clip tuning.** One configuration for the whole set. Settings that depend on the picture (pitcher location, size) are found from the clip, not typed in.
3. **Audit output.** Every processed clip writes a small image strip around the detected release plus a JSON record (release frame, confidence, which checks passed) so any result can be checked in seconds.
4. **Batch.** A folder of clips runs without manual steps, resumes after interruption, and one bad clip does not stop the rest. Time per clip is recorded.
5. **Tests.** Unit tests on synthetic video for the tracker and the checks; a regression test on the development clips that skips when the clips are absent.

## Reporting

Per-clip table (label A, label B, detector, error), the metrics above with counts, and a list of every clip that failed or was off by more than 1 frame with its audit strip. Failures are fixed only by changing the general method and re-running the whole set, never one clip.
