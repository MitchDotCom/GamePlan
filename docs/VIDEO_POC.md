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
