"""Proof of concept: pitch-level video from public sources, cut at release with no manual step.

Chain (each step verified on live data, see docs/VIDEO_POC.md):
  1. Savant game feed  baseballsavant.mlb.com/gf?game_pk=...   -> one record per pitch with play_id, plateTime, trajectory
  2. Savant video page baseballsavant.mlb.com/sporty-videos?playId=<play_id> -> the pitch's mp4 URL on sporty-clips.mlb.com
  3. Download the mp4 (needs a browser User-Agent and a Savant referer, otherwise the CDN returns a Cloudflare 403)
  4. Find the arrival sound (bat crack or mitt pop) in the audio; release = arrival - plateTime
  5. Cut with ffmpeg around release

Only step 4's rule is a hypothesis; probe() writes the evidence needed to accept or reject it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import time
import urllib.request

import numpy as np

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
REFERER = "https://baseballsavant.mlb.com/"
SAVANT = "https://baseballsavant.mlb.com"


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _get(url: str, binary: bool = False, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER, "Accept": "*/*"})
    data = urllib.request.urlopen(req, timeout=timeout).read()
    return data if binary else data.decode("utf-8", "replace")


def game_pitches(game_pk: int | str) -> list[dict]:
    d = json.loads(_get(f"{SAVANT}/gf?game_pk={game_pk}"))
    return (d.get("team_home") or []) + (d.get("team_away") or [])


def clip_url(play_id: str) -> str | None:
    html = _get(f"{SAVANT}/sporty-videos?playId={play_id}")
    m = re.search(r"https://sporty-clips\.mlb\.com/[^\"' ]+\.mp4", html)
    return m.group(0) if m else None


def download(url: str, path: pathlib.Path) -> pathlib.Path:
    path.write_bytes(_get(url, binary=True, timeout=120))
    return path


def video_info(path: pathlib.Path):
    import cv2
    c = cv2.VideoCapture(str(path))
    return dict(fps=c.get(cv2.CAP_PROP_FPS), frames=int(c.get(cv2.CAP_PROP_FRAME_COUNT)), w=int(c.get(cv2.CAP_PROP_FRAME_WIDTH)), h=int(c.get(cv2.CAP_PROP_FRAME_HEIGHT)))


def scene_cuts(path: pathlib.Path, thresh: float = 25.0) -> list[float]:
    """Seconds at which the picture changes abruptly (mean absolute grey difference on a 160x90 copy)."""
    import cv2
    c = cv2.VideoCapture(str(path))
    fps = c.get(cv2.CAP_PROP_FPS)
    prev, out, i = None, [], 0
    while True:
        ok, f = c.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(f, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None and float(np.abs(g - prev).mean()) > thresh:
            out.append(round(i / fps, 3))
        prev = g
        i += 1
    return out


def audio_envelope(path: pathlib.Path, win: float = 0.010):
    """Impulse energy of the audio (energy of the first difference, which favours sharp sounds), per 10 ms window, as (times, values)."""
    sr = 16000
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    if len(a) < sr:
        return np.array([]), np.array([])
    d = np.diff(a, prepend=0.0)
    w = int(win * sr)
    n = len(d) // w
    e = np.sqrt((d[: n * w].reshape(n, w) ** 2).mean(axis=1))
    return np.arange(n) * win, e


def audio_peaks(path: pathlib.Path, k: int = 3, min_gap: float = 0.4):
    """The k strongest impulse times (seconds, relative strength), at least min_gap apart."""
    t, e = audio_envelope(path)
    if len(e) == 0:
        return []
    order = np.argsort(-e)
    chosen = []
    for i in order:
        if all(abs(t[i] - c[0]) >= min_gap for c in chosen):
            chosen.append((float(t[i]), float(e[i] / e.max())))
        if len(chosen) == k:
            break
    return chosen


def cut(path: pathlib.Path, start: float, end: float, out: pathlib.Path) -> pathlib.Path:
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(path), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(out)], check=True)
    return out


def frame_strip(path: pathlib.Path, times: list[float], out: pathlib.Path, width: int = 400, labels: list[str] | None = None):
    import cv2
    c = cv2.VideoCapture(str(path))
    fps = c.get(cv2.CAP_PROP_FPS)
    tiles = []
    for j, t in enumerate(times):
        c.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(t * fps))))
        ok, f = c.read()
        if not ok:
            f = np.zeros((720, 1280, 3), np.uint8)
        f = cv2.resize(f, (width, int(width * 9 / 16)))
        cv2.putText(f, labels[j] if labels else f"{t:.2f}s", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        tiles.append(f)
    cols = 4
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))


def pick_sample(pitches: list[dict], per_kind: int = 2, seed: int = 4):
    """A fixed-seed mix of outcomes so the arrival-sound rule is tried on swings, takes and balls in play."""
    rng = np.random.default_rng(seed)
    kinds = {"called strike": lambda p: p.get("description") == "Called Strike", "swinging strike": lambda p: "Swinging Strike" in (p.get("description") or ""),
             "ball": lambda p: p.get("description") in ("Ball", "Ball In Dirt"), "foul": lambda p: p.get("description") in ("Foul", "Foul Tip"),
             "in play": lambda p: "In play" in (p.get("description") or "")}
    out = []
    for k, f in kinds.items():
        pool = [p for p in pitches if f(p) and p.get("play_id") and p.get("plateTime")]
        idx = rng.permutation(len(pool))[:per_kind]
        out += [(k, pool[i]) for i in idx]
    return out


def probe(game_pk: int, workdir: pathlib.Path, per_kind: int = 2) -> list[dict]:
    workdir.mkdir(parents=True, exist_ok=True)
    pitches = game_pitches(game_pk)
    rows = []
    for kind, p in pick_sample(pitches, per_kind):
        row = dict(kind=kind, play_id=p["play_id"], pitch=p.get("pitch_name"), speed=p.get("start_speed"), plateTime=p["plateTime"],
                   desc=p.get("description"), inning=p.get("inning"), pitcher=p.get("pitcher_name"), batter=p.get("batter_name"))
        try:
            url = clip_url(p["play_id"])
            if not url:
                row["error"] = "no mp4 link on video page"
                rows.append(row)
                continue
            path = download(url, workdir / f"{p['play_id']}.mp4")
            info = video_info(path)
            row.update(info, cuts=scene_cuts(path), peaks=[(round(t, 2), round(s, 2)) for t, s in audio_peaks(path)])
        except Exception as e:
            row["error"] = str(e)[:120]
        rows.append(row)
        time.sleep(0.5)
    return rows


# ---------------------------------------------------------------- game package: select, find release, cut, answer key

SIDE_CUT = 0.28          # feet; same inside/middle/away cut as the validated S2 grid
ZONE_HALF_WIDTH = 0.83   # feet; plate half-width plus one ball radius


def pitch_family(pitch_type: str) -> str:
    from .coach import FAMILY_OF
    return FAMILY_OF.get(pitch_type, "OTH")


def pocket(p: dict) -> str | None:
    """Nine-pocket name (height third x inside/middle/away) from tracking: 'low-away', 'high-in', 'mid-mid' and so on."""
    try:
        px, pz, top, bot, stand = float(p["px"]), float(p["pz"]), float(p["sz_top"]), float(p["sz_bot"]), p.get("stand")
    except (KeyError, TypeError, ValueError):
        return None
    if stand not in ("L", "R") or top <= bot:
        return None
    zr = (pz - bot) / (top - bot)
    height = "low" if zr < 1 / 3 else "mid" if zr < 2 / 3 else "high"
    away = px if stand == "R" else -px          # + = away from the batter
    side = "in" if away < -SIDE_CUT else "away" if away > SIDE_CUT else "mid"
    return f"{height}-{side}"


def answer_keys(p: dict) -> dict:
    """Go/no-go truth from tracking, no hand labeling. Pitch go/no-go: Go on fastballs. Zone go/no-go: Go on pitches through the zone."""
    fam = pitch_family(p.get("pitch_type", ""))
    try:
        in_zone = abs(float(p["px"])) <= ZONE_HALF_WIDTH and float(p["sz_bot"]) <= float(p["pz"]) <= float(p["sz_top"])
    except (KeyError, TypeError, ValueError):
        in_zone = None
    return dict(family=fam, pitch_go=(fam == "FB"), zone_go=in_zone)


def pitch_meta(p: dict) -> dict:
    """What a trial log needs to know about the pitch: type, family, pocket, location, zone, speed, sides. Values from tracking, nothing inferred."""
    return dict(pitch_type=p.get("pitch_type"), family=pitch_family(p.get("pitch_type", "")), pocket=pocket(p), px=p.get("px"), pz=p.get("pz"), sz_top=p.get("sz_top"),
                sz_bot=p.get("sz_bot"), speed=p.get("start_speed"), stand=p.get("stand"), p_throws=p.get("p_throws"))


def top_shapes(pitches: list[dict], pitcher: str, stand: str, n: int = 3) -> list[tuple]:
    """The pitcher's n most-used (family, pocket) shapes against batters of this side. Usage only: the validated rule (V2) found no model beats it."""
    from collections import Counter
    c = Counter((pitch_family(p.get("pitch_type", "")), pocket(p)) for p in pitches
                if p.get("type") == "pitch" and p.get("stand") == stand and pocket(p) and pitcher.lower() in (p.get("pitcher_name") or "").lower())
    return [k for k, _ in c.most_common(n)]


def select(pitches: list[dict], pitcher: str | None = None, families: tuple = (), pockets: tuple = (), limit: int = 10, seed: int = 1,
           stand: str | None = None, shapes: tuple = ()) -> list[dict]:
    """Rows from the tracking feed that match the request, in a fixed-seed order. `shapes` is a set of (family, pocket) pairs."""
    out = []
    for p in pitches:
        if stand and p.get("stand") != stand:
            continue
        if shapes and (pitch_family(p.get("pitch_type", "")), pocket(p)) not in shapes:
            continue
        if p.get("type") != "pitch" or not p.get("play_id") or not p.get("plateTime"):
            continue
        if pitcher and pitcher.lower() not in (p.get("pitcher_name") or "").lower():
            continue
        if families and pitch_family(p.get("pitch_type", "")) not in families:
            continue
        pk = pocket(p)
        if pockets and pk not in pockets:
            continue
        out.append(p)
    order = np.random.default_rng(seed).permutation(len(out))
    return [out[i] for i in order[:limit]]


ARRIVAL_WINDOW = (3.0, 4.0)   # seconds into a Savant clip where the arrival sound falls (learned from 65 MLB clips, not guaranteed by the feed)
MIN_PEAK_SHARE = 0.5          # window peak must be at least this share of the clip's loudest sound, else the pitch is skipped


def find_release(path: pathlib.Path, plate_time: float):
    """(release_seconds, arrival_seconds, confidence, source) or None. Source 'audio' is the MLB-broadcast anchor; Visalia video needs a visual anchor."""
    t, e = audio_envelope(path)
    if len(e) == 0:
        return None
    m = (t >= ARRIVAL_WINDOW[0]) & (t <= ARRIVAL_WINDOW[1])
    if not m.any():
        return None
    i = int(np.argmax(np.where(m, e, -1)))
    share = float(e[i] / e.max())
    if share < MIN_PEAK_SHARE:
        return None
    arrival = float(t[i])
    return arrival - plate_time, arrival, share, "audio"


def build_package(p: dict, workdir: pathlib.Path, offset: float = 0.150, preroll_max: float = 1.6, reveal_tail: float = 1.0, crop_bottom: float = 0.12) -> dict:
    """One pitch -> two files and a manifest row. Pre file ends `offset` seconds after release, has no audio, and has the bottom `crop_bottom` of the picture removed
    (broadcast scoreboards show pitch type and speed after the pitch; removing them stops an answer leak). Reveal file continues to just after arrival."""
    pid = p["play_id"]
    out = dict(play_id=pid, pitcher=p.get("pitcher_name"), batter=p.get("batter_name"), inning=p.get("inning"), count=f"{p.get('balls')}-{p.get('strikes')}",
               pitch_type=p.get("pitch_type"), speed=p.get("start_speed"), pocket=pocket(p), result=p.get("description"), plateTime=p["plateTime"], **answer_keys(p))
    url = clip_url(pid)
    if not url:
        return dict(out, status="no clip link")
    src = download(url, workdir / f"{pid}.mp4")
    rel = find_release(src, float(p["plateTime"]))
    if not rel:
        return dict(out, status="release not found (no clear arrival sound in window)")
    release, arrival, conf, source = rel
    cuts = scene_cuts(src)
    start = max(0.0, release - preroll_max)
    early = [c for c in cuts if 0.2 < c < release - 0.4]
    if early:
        start = max(start, early[-1])
    pause = release + offset
    later = [c for c in cuts if c > arrival - 0.05]
    end = min(arrival + reveal_tail, later[0] if later else arrival + reveal_tail)
    pre, rev = workdir / f"{pid}_pre.mp4", workdir / f"{pid}_reveal.mp4"
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(src), "-ss", f"{start:.3f}", "-to", f"{pause:.3f}", "-an", "-vf", f"crop=iw:trunc(ih*{1 - crop_bottom}/2)*2:0:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(pre)], check=True)
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(src), "-ss", f"{pause:.3f}", "-to", f"{end:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(rev)], check=True)
    return dict(out, status="ok", release=round(release, 3), arrival=round(arrival, 3), confidence=round(conf, 2), release_source=source, start=round(start, 3), pause=round(pause, 3),
                end=round(end, 3), offset=offset, crop_bottom=crop_bottom, pre_file=pre.name, reveal_file=rev.name)


def build_set(game_pk: int, workdir: pathlib.Path, **selection) -> list[dict]:
    workdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in select(game_pitches(game_pk), **selection):
        try:
            rows.append(build_package(p, workdir))
        except Exception as e:
            rows.append(dict(play_id=p["play_id"], status=f"error: {str(e)[:100]}"))
        time.sleep(0.4)
    (workdir / "manifest.json").write_text(json.dumps(rows, indent=1))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=int, required=True)
    ap.add_argument("--work", default="/tmp/claude-0/clips/probe")
    ap.add_argument("--per-kind", type=int, default=2)
    ap.add_argument("--build", action="store_true", help="select pitches, cut pre-pause and reveal files, write manifest.json")
    ap.add_argument("--pitcher", default=None)
    ap.add_argument("--families", default="")
    ap.add_argument("--pockets", default="")
    ap.add_argument("--limit", type=int, default=6)
    a = ap.parse_args(argv)
    if a.build:
        rows = build_set(a.game, pathlib.Path(a.work), pitcher=a.pitcher, families=tuple(x for x in a.families.split(",") if x), pockets=tuple(x for x in a.pockets.split(",") if x), limit=a.limit)
        for r in rows:
            print(json.dumps(r))
        return 0
    rows = probe(a.game, pathlib.Path(a.work), a.per_kind)
    pathlib.Path(a.work, "probe.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
