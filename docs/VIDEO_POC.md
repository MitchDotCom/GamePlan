# Video proof of concept, status 2026-10-07

Goal (owner): go/no-go training game. The pitch clip plays, pauses a set time after release, the hitter hits Go or No-Go, then the rest plays and the answer is scored. Release and pause must be found with no manual step. Code: `src/gameplan/videocut.py`.

## Verified on live data (MLB, 2025-06-10 games, Savant)

| Step | What was checked | Result |
|---|---|---|
| Per-pitch data | `baseballsavant.mlb.com/gf?game_pk=...` | One record per pitch with `play_id`, `plateTime`, extension, trajectory, `sportId`, pitch type, description. Works with a plain curl-style client |
| Clip link | `baseballsavant.mlb.com/sporty-videos?playId=<play_id>` | Page contains a direct mp4 link on `sporty-clips.mlb.com`. Found for all 65 pitches tried (15 + 50) |
| Download | mp4 from the CDN | Works with a browser User-Agent and a Savant referer. A default client gets a Cloudflare 403. The domain had to be allowed in this environment's network policy (done by owner) |
| Clip format | 65 clips | 1280x720, about 59.6 fps, H.264 plus AAC audio. Median length 7.0 s (range 5.9 to 28.8 s). Longer clips for balls in play (replay and result angles follow) |
| Clip structure (one clip examined frame by frame) | cuts at 0.34, 4.12 and 9.11 s | Batter close-up, then about 3.8 s of center-field view with pitcher, batter and catcher, then the field after contact, then a pitcher close-up. Camera cuts do NOT mark release or contact (the cut came 0.7 s after contact) |
| Audio | 65 clips | Every clip has a dominant sharp sound inside the pitch segment |

## The release rule being tested

Release = time of the arrival sound (bat crack or mitt pop) minus `plateTime` from tracking.

- Arrival sound, strongest sound between 3.2 and 3.8 s, 50 random pitches from 5 games: median 3.48 s, sd 0.071 s, range 3.28 to 3.64 s. Same for takes, whiffs, fouls and balls in play (medians 3.45 to 3.53 s). 46 of 50 had a window peak at least 75% of the clip's loudest sound.
- In 8 of 50 clips the loudest sound in the whole clip was elsewhere (crowd or announcer), so a rule that takes the loudest sound anywhere fails 16% of the time. Restricting to the window 3.2 to 3.8 s fixes that, but that window is learned from these clips, not a known property of the feed.
- Implied release: mean 3.046 s, sd 0.067 s.
- Slope of arrival time on `plateTime` across clips: 0.87 (standard error roughly 0.3 by my arithmetic, not computed in code). Between "aligned on arrival" (0) and "aligned on release" (1). Suggests clips are cut with a roughly fixed lead before release, but this is not established.
- Visual check against the frames on 4 clips, tight crop, 2-frame steps (33 ms): 3 readable clips showed the ball leaving or just left the hand within about one to two frames of the estimate (about -0.03 to +0.00 s). 1 clip was not readable. This is my reading by eye on 3 pitches.

## What this does and does not show

Shows: the CSV-to-clip join works with no manual step, and the audio rule is a candidate for release timing.

Does not show: that release is found to within a frame. The spread of 0.067 s could be real clip-alignment jitter or detector noise, and I cannot tell which from timing alone. If the occlusion pause is placed 100 ms after release, a 67 ms error is a large share of it. If the pause is 200 ms or later it matters less.

## Not yet verified (no claims)

1. Release accuracy against ground truth. Needs release labeled on about 20 clips and the error distribution measured.
2. An automatic visual release detector (ball leaving the hand) as a second anchor. Not built.
3. Which occlusion offsets are right for training. Needs the pilot.
4. Minor-league clips. The game feed returns non-MLB games (`sportId` 16 and 23 appeared for two game IDs), but I have not checked clips for any of them and do not know which leagues they are. I need a verified minor-league `game_pk` to test.
5. Camera angle. All clips so far show the center-field broadcast view. No low-home or open-side angle was found in this source.
6. Scoring truth for go/no-go (pitch type, or ball/strike from the zone) is available from tracking, not tested in the game flow.

## Minor-league test, game_pk 821376 (provided by owner), 2026-10-07

Game: Visalia Rawhide at Fresno Grizzlies, Chukchansi Park, 2026-08-06, `sportId` 14 (Single-A). Checked against Savant's game feed and video pages.

| Item | Result |
|---|---|
| Game feed | Returns the game. 240 records, 238 pitches, every one with a `play_id` |
| Fields present | Inning, count, batter, pitcher, catcher, result and description, strike-zone top, bottom and width, `stand`, `p_throws`. Batted-ball location (`hc_x`, `hc_y`) on balls in play only |
| Tracking fields | **Absent:** pitch type, speed, plate location (`px`, `pz`), `plateTime`, extension, break, spin. These keys do not exist in the records |
| Video | Savant's video page for 12 random pitches from this game: **0 of 12** have a clip link. The same page for an MLB pitch has one |
| Savant "Minor League Search" | Exists on the site. Its Level control is built by script I could not read, so I do not know what level values it accepts. Earlier attempts to pull minor-league data through the search CSV returned MLB games |

Conclusions that hold:
1. For this California League game, public Savant has play-by-play but no pitch tracking and no video. A Visalia proof of concept cannot be built from public data. The chain tested on MLB games (pitch data to play_id to clip) does not extend to this game.
2. The Visalia version has to run on the org's own tracking export and the org's own video (angles and quality as the owner described: low home, open-side pitcher, center field; 1080p, 60 fps).

What I do not know (so no claims):
- Whether the org's video carries a clock or timecode that can be matched to the tracking export's pitch timestamps. If so, release can be anchored without audio or computer vision. If not, release has to come from the video itself.
- Whether the org's video has audio. The audio rule tested here relies on broadcast audio.
- Whether other minor-league levels or games have clips on Savant. One game and 12 pitches is all that was tried.

## Plan that follows from this

The engine should treat the release time as coming from one of three interchangeable sources, in order of preference, and say which one it used for each pitch:
1. Tracking timestamp matched to video clock (if the org data supports it). Not testable here.
2. Arrival sound minus flight time. Works on broadcast-style clips with audio, accuracy not yet established.
3. A visual ball-leaves-hand detector. Not built.
Proving 2 and 3 on MLB broadcast video is possible now. Proving 1 needs one Visalia tracking file and a matching video.

## MLB proof of concept, end to end (2026-10-07)

Command: `python -m gameplan.videocut --game 777433 --build --work <dir> --pitcher Singer --families BRK,OFF --limit 6` (pitch data in, clip files and manifest out, no manual step).

What it does per pitch:
1. Selects pitches from the tracking feed by pitcher, pitch family and pocket. Pocket is the nine-pocket grid used in the validated S2 shape (height third x inside/middle/away, cut at 0.28 ft), from `px`, `pz`, `sz_top`, `sz_bot` and `stand`.
2. Gets the clip link and downloads the clip.
3. Finds release: arrival sound inside 3.0 to 4.0 s of the clip, minus `plateTime`. A pitch is skipped (not hand-fixed) when the window's loudest sound is under half of the clip's loudest.
4. Cuts two files with ffmpeg: **pre** (from the last camera cut before release, or 1.6 s of lead-in, to release + 150 ms, no audio, bottom 12% of the picture removed) and **reveal** (from the pause to just after arrival or the next camera cut).
5. Writes the answer key from tracking: pitch go/no-go (Go on fastballs) and zone go/no-go (Go on pitches through the zone), plus pitch type, speed, pocket and result.

Run on 6 Brady Singer breaking and offspeed pitches: 6 of 6 produced packages. Pre files are 1.75 s, 105 frames at 59.94 fps. Reveal files are about 1.3 s.

## Release accuracy, what was measured

I labeled the first frame where the ball is clearly separate from the fingertips, by eye at 1-frame steps, on 8 of the 15 probe clips. Readable on 5:

| Clip | Pitch | Label (frames from the audio estimate) | Basis |
|---|---|---|---|
| c0 | Sweeper, called strike | -1 | ball clearly free |
| c8 | Fastball, ball | -1 | ball clearly free |
| c12 | Fastball, in play | +1 | ball adjacent at 0, clearly free at +1 |
| c3 | Fastball, swinging strike | about -1 | arm at full extension, ball not visible against white lettering |
| c4 | Fastball, swinging strike | about -1 | same |

So the audio-based estimate is within 1 to 2 frames (17 to 33 ms) of the labeled release on 5 of 5, usually about one frame late. Three of the other clips (c1, c2, c6) could not be read. This is five clips, read by eye. A likely cause of the lateness: `plateTime` is time to the front of the plate and the mitt sound comes a little later, but I have not tested that.

A separate check: an automatic ball tracker (white blob, frame differencing, region of interest) followed the ball in clip 0 from +3 to +18 frames at about 7.5 pixels per frame, matching the position I read by eye. Extending that track back to the hand puts release near -0.6 frames, in line with the -1 label. It cannot replace the audio rule yet: it picks the ball up a few frames after release, and it lost the ball behind the batter before arrival.

## Problems found

1. **The ball is a few pixels wide at the pause point in this view.** At 150 ms after release, in the center-field broadcast view at 1280x720, the ball is about 6 to 8 pixels and not discernible in thumbnails. Pitch-recognition cues (spin, shape) are not visible. This feed is good for proving the pipeline, not for training. A closer angle (low home, 1080p) is much more likely to work; I could not test that here.
2. **Answer overlay.** The broadcast graphic shows pitch type and speed after the pitch ("SWEEPER 81 MPH"). It was not on screen at the pause in these six clips, but the pre file crops the bottom 12% by default so it cannot leak. The crop assumes the scoreboard is at the bottom, which held for the broadcasts seen here and is not guaranteed.
3. **The release anchor is MLB-broadcast specific.** Audio is not usable on Visalia video (owner: volume unreliable) and there is no video clock to match to tracking timestamps (owner). So the Visalia version needs a visual anchor. The ball tracker above is the starting point. The audio rule remains useful as an independent check for a visual method on MLB clips.
4. **The 3.0 to 4.0 s window** comes from the feed's clip alignment, learned from 65 clips.

## Next

Build a visual release detector (ball track plus the pitcher's arm motion) and measure it against the audio rule on a few hundred MLB clips and against the hand labels on the readable ones. Then test it on closer-angle video when available.

## Other camera angles (owner asked for MLB low home), checked 2026-10-07

Result: **no other angle reachable from here.** Only the HOME broadcast feed is served.

- Savant's video page sets `feedType = 'HOME'` in its script. Passing `feedType=AWAY`, `NETWORK` or `CENTERFIELD` in the URL changes nothing (same mp4 each time).
- Savant's game feed records have no other video fields among those inspected.
- A long clip (18.3 s, a ball in play) was checked at 0.7 s steps: one continuous broadcast of the play (batter close-up, center-field pitch view, outfield, base running). No replay from another angle.
- Hosts blocked by this environment's network policy and therefore not tested: `statsapi.mlb.com`, `www.milb.com`, `cuts.diamond.mlb.com`. Whether they hold other angles is unknown.
- Two web searches found nothing on public downloads of other MLB camera angles. They did confirm that Hawk-Eye uses several cameras (reported as four behind the plate and one in center field for pitch tracking), but that is tracking hardware, not a public video source.

Consequence: the MLB proof of concept stays on the center-field broadcast view. The pipeline, the answer key and the cutting are angle-independent. The release detector and whether the ball is visible at the pause are not, and need a closer angle to settle.

## After the owner allowed more hosts (2026-10-07)

Reachable now: `statsapi.mlb.com` (schedule, live game feed, game content all return data, for MLB and for sportId 14). Still not reachable: `mlb-cuts-diamond.mlb.com` (the host of the highlight mp4s, connection refused by policy), `www.mlb.com/video`. `cuts.diamond.mlb.com` and `www.milb.com` answer at the root (403 and a redirect), not tested further.

- **Game content (MLB, CIN@STL 2025-06-20):** 28 highlight items. They are game-level edits (condensed game, recap, key plays, interviews), 1280x720 at about 59 fps, 4 to 16 Mbps. They carry no play IDs, no camera-angle tags, and are not per pitch. Keyword types: game, team, player, taxonomy, season.
- **Game content (Single-A, Visalia at Fresno, 821376):** no highlights at all.
- **Live game feed, Single-A (821376):** 238 pitches, each with a `playId`, strike-zone top and bottom, and plate coordinates. No pitch type, speed, flight time, extension or break (the same gap as the Savant feed). No video or camera fields anywhere in the feed.
- **Live game feed, MLB (777433):** full tracking on all 305 pitches. No video or camera fields.

Conclusion: opening statsapi did not produce another camera angle or any Single-A tracking or clips. A low-home view for MLB is not available from anything I can reach. The owner's own footage is the only low-home source.
