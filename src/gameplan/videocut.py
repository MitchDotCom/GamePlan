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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=int, required=True)
    ap.add_argument("--work", default="/tmp/claude-0/clips/probe")
    ap.add_argument("--per-kind", type=int, default=2)
    a = ap.parse_args(argv)
    rows = probe(a.game, pathlib.Path(a.work), a.per_kind)
    pathlib.Path(a.work, "probe.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
