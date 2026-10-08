"""Visalia path: TrackMan export + low-home clips -> a hitter's go/no-go page, and a pull list of the pitches that still need a clip.

No video timestamp match exists, so a clip is tied to a pitch in one of two explicit ways, and anything unclear is refused, never guessed:
  --manifest  CSV with columns clip,pitch_uid       (clip = file name with or without extension)
  --name-pattern  a regex with named groups matched against the clip file name; groups date, inning, pa, pitch map to TrackMan Date, Inning, PAofInning, PitchofPA.
                  Example: "(?P<date>\\d{8})_inn(?P<inning>\\d+)_pa(?P<pa>\\d+)_p(?P<pitch>\\d+)"
A clip that matches zero or more than one pitch, or two clips for one pitch, is listed under `problems` and left out.

  python -m gameplan.visalia --trackman export.csv --pitcher-id 123 --before 2026-05-02 --starts 5 --hitter-id 456 --stand L --name usage \
      --clips <folder> --manifest m.csv --profile config/lowhome_profiles/visalia_low_home_dev.json --out <dir>

Outputs in <dir>: needs_clips.csv (every playlist pitch with its identifying fields and whether a clip was found), gonogo.html (pitches that have a clip), report.json.
Answer keys come from the TrackMan row (zone: ball in the zone using the default zone unless heights are supplied; pitch: fastball family); no key is invented for a missing field.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re

from . import lowhome_demo as LD
from . import lowhome_release as L
from . import playlist as PL
from . import trackman as TM
from . import videocut as V

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".avi", ".mkv")
GROUP_TO_FIELD = {"date": "_date", "inning": "inning", "pa": "pa", "pitch": "pitch_of_pa"}


def _norm(field: str, v) -> str:
    s = str(v).strip()
    if field == "_date":
        return re.sub(r"\D", "", s)
    try:
        return str(int(float(s)))
    except ValueError:
        return s


def read_manifest(path: pathlib.Path) -> dict:
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        out[pathlib.Path(r["clip"]).stem] = r["pitch_uid"]
    return out


def match_by_name(clips: list[pathlib.Path], pitches: list[dict], pattern: str) -> tuple[dict, list]:
    """({clip stem: play_id}, problems). Only unique matches are kept."""
    rx = re.compile(pattern)
    out, problems = {}, []
    for c in clips:
        m = rx.search(c.stem)
        if not m:
            problems.append((c.name, "file name does not match the pattern"))
            continue
        keys = {GROUP_TO_FIELD[g]: v for g, v in m.groupdict().items() if g in GROUP_TO_FIELD and v is not None}
        hits = [p for p in pitches if all(_norm(f, p.get(f)) == _norm(f, v) for f, v in keys.items())]
        if len(hits) == 1:
            out[c.stem] = hits[0]["play_id"]
        else:
            problems.append((c.name, f"{len(hits)} pitches match {keys}"))
    return out, problems


def build(trackman_csv: str, pitcher_id, before: str, n_starts: int, hitter_id, stand: str, name: str, clips_dir: pathlib.Path, out: pathlib.Path,
          profile: L.CameraProfile, manifest: pathlib.Path | None = None, name_pattern: str | None = None, limit: int = 8, n_shapes: int = 3) -> dict:
    if not manifest and not name_pattern:
        raise ValueError("give --manifest or --name-pattern: there is no timestamp match, so a clip cannot be tied to a pitch any other way")
    out.mkdir(parents=True, exist_ok=True)
    rows = TM.read(trackman_csv)
    signs = TM.infer_signs(rows)
    pitches = TM.convert(rows, signs)
    pool = TM.pool(pitches, pitcher_id, n_starts, before)
    hitter = dict(stand=stand, name=str(hitter_id), rows=TM.hitter_rows(rows, signs, hitter_id))
    pl = PL.playlist(name, pool, hitter, n_shapes, 10 ** 6)
    wanted = pl["pitches"][:limit * 4]
    clips = sorted(p for p in clips_dir.iterdir() if p.suffix.lower() in VIDEO_EXT)
    problems = []
    if manifest:
        by_clip = read_manifest(manifest)
    elif name_pattern:
        by_clip, problems = match_by_name(clips, pool, name_pattern)
    clip_of = {}
    for stem, uid in by_clip.items():
        if uid in clip_of:
            problems.append((stem, f"pitch {uid} already has clip {clip_of[uid]}"))
            clip_of.pop(uid)
            continue
        clip_of[uid] = stem
    by_stem = {c.stem: c for c in clips}
    use, answers = [], {}
    with open(out / "needs_clips.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pitch_uid", "date", "inning", "pa", "pitch_of_pa", "batter", "count", "pitch_type", "pocket", "speed", "clip"])
        for p in wanted:
            stem = clip_of.get(p["play_id"])
            w.writerow([p["play_id"], p["_date"], p.get("inning"), p.get("pa"), p.get("pitch_of_pa"), p.get("batter_name"), f"{p['balls']}-{p['strikes']}", p["pitch_type"],
                        V.pocket(p), p["start_speed"], stem or ""])
            if stem and stem in by_stem and len(use) < limit:
                k = V.answer_keys(p)
                use.append(str(by_stem[stem]))
                answers[stem] = dict(zone_go=k["zone_go"], pitch_go=k["pitch_go"], result=f"{p['pitch_type']} {p['start_speed']} mph, {V.pocket(p)}, {p.get('pitch_call')}", meta=V.pitch_meta(p))
    items = LD.build(use, out / "gonogo.html", profile, answers) if use else []
    rep = dict(playlist=name, shapes=[list(s) for s in pl["shapes"]], evidence=pl["evidence"], pool_pitches=len(pool), playlist_pitches=len(wanted), with_clip=len(use),
               pages_built=len(items), problems=problems, signs=dict(plate=signs.plate, arm=signs.arm))
    if pl.get("note"):
        rep["trait"] = pl["note"]
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trackman", required=True)
    ap.add_argument("--pitcher-id", required=True)
    ap.add_argument("--before", required=True)
    ap.add_argument("--starts", type=int, default=5)
    ap.add_argument("--hitter-id", required=True)
    ap.add_argument("--stand", choices=["L", "R"], required=True)
    ap.add_argument("--name", choices=sorted(PL.GENERATORS), default="usage")
    ap.add_argument("--clips", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--name-pattern", default=None)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    rep = build(pathlib.Path(a.trackman).read_text(encoding="utf-8-sig"), a.pitcher_id, a.before, a.starts, a.hitter_id, a.stand, a.name, pathlib.Path(a.clips), pathlib.Path(a.out),
                L.CameraProfile.from_json(pathlib.Path(a.profile).read_text()), pathlib.Path(a.manifest) if a.manifest else None, a.name_pattern, a.limit)
    print(json.dumps(rep, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
