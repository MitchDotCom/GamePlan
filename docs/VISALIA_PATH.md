# Visalia path: TrackMan + low-home clips, 2026-10-08

Code: `src/gameplan/visalia.py` (uses `trackman.py`, `playlist.py`, `lowhome_demo.py`, `lowhome_release.py`). Tests: `tests/test_visalia.py`.

## The clip join (open item 7)
There is no video timestamp match, so a clip can be tied to a pitch only by something explicit:
- **Manifest:** a CSV `clip,pitch_uid` that staff or an export produces.
- **File-name pattern:** a regex with named groups `date`, `inning`, `pa`, `pitch` matched to TrackMan Date, Inning, PAofInning, PitchofPA. The match must be unique.

Zero matches, several matches, a file name that does not fit, or two clips for one pitch are all listed under `problems` and left out. Nothing is guessed. It does not yet check the join itself (for example by comparing the clip's flight time with TrackMan's ZoneTime); a wrong manifest would go through.

## What the command makes
`python -m gameplan.visalia --trackman export.csv --pitcher-id .. --before .. --starts N --hitter-id .. --stand L|R --name usage|ride|run --clips <folder> --manifest m.csv|--name-pattern RE --profile <profile.json> --out <dir>`
1. `needs_clips.csv`: every pitch in the hitter's playlist (date, inning, PA, pitch of PA, batter, count, pitch type, pocket, speed) and the clip if one was found. This is the pull list for video staff, and it works with no clips at all.
2. `gonogo.html`: a page for the pitches that have a clip. Release frame comes from the low-home detector; answer keys come from the TrackMan row.
3. `report.json`: shapes, evidence tag, pool size, clips found, problems, inferred signs.

## Dry run (plumbing only)
Three real low-home clips, a synthetic TrackMan export (1,600 pitches across six dates, one pitcher), and a manifest I wrote mapping the clips to three playlist pitches. Pass 1 with an empty manifest: 1,333 pooled pitches, 32 playlist pitches, 0 clips, a pull list written. Pass 2: 3 clips matched, 3 pages built, release frames 456, 396, 418 as before, no problems. This shows the pieces connect. It says nothing about baseball, because the TrackMan side is synthetic and the clips do not belong to those pitches.

## Not done
- The join is unverified against content. A clip-to-pitch check from the video itself is open.
- Zone answer key uses the default 1.5 to 3.5 ft zone unless per-batter heights are supplied.
- The detector has been tested on 3 clips (tuned on them). The held-out acceptance test (30 or more clips, two labelers) is still the gate before this runs on real pitches.
