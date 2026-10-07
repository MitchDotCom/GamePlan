"""Visual-only release finder for a fixed camera behind home plate (the 'low home' view). No audio, no tracking timestamp.

Steps, all from pixels:
  1. Pitcher box: the pitcher stands still on the rubber before the windup, so the box is the region around the start-of-clip
     bright-uniform blob nearest the mound line (config below; adjustable per camera).
  2. Delivery window: the burst of motion inside that box.
  3. Ball track: small bright blobs that are not present in the same place a few frames earlier or later (so not static),
     linked frame to frame into a track that falls toward the plate.
  4. Release = first frame of the ball track, minus a lag that is calibrated against hand-labeled frames (see docs/LOWHOME_POC.md).

Everything here was developed on three Visalia low-home clips. It is a starting point, not a validated method.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import cv2
import numpy as np

# Pitcher box and ball corridor for the Visalia low-home camera (1280x720). Other cameras need their own.
PITCHER_BOX = (540, 40, 780, 290)      # x0, y0, x1, y1 : where the pitcher stands and winds up
BALL_ROI = (500, 60, 840, 720)         # x0, y0, x1, y1 : where the ball travels toward the plate
WHITE_MIN = 185                         # min(B,G,R) at or above this counts as ball-white
NEUTRAL_MAX = 60                        # max-min channel spread allowed (rejects colored objects)
AREA = (12, 220)                        # pixel area of a ball blob
STATIC_GAP = 4                          # a blob is static if white sits there this many frames earlier or later
LINK_MAX = 40                           # max px a ball moves between consecutive frames
MIN_TRACK = 5                           # frames (the ball is visible for only 6 to 8 frames before the net and background hide it)


def read_gray_white(frames):
    out = []
    for f in frames:
        b, g, r = [f[:, :, i].astype(np.int16) for i in range(3)]
        mn, mx = np.minimum(np.minimum(b, g), r), np.maximum(np.maximum(b, g), r)
        out.append(((mn >= WHITE_MIN) & ((mx - mn) <= NEUTRAL_MAX)).astype(np.uint8))
    return out


def motion_energy(path: str, box=PITCHER_BOX):
    c = cv2.VideoCapture(path)
    fps = c.get(cv2.CAP_PROP_FPS)
    x0, y0, x1, y1 = box
    prev, en = None, []
    while True:
        ok, f = c.read()
        if not ok:
            break
        g = cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        en.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
    return np.array(en), fps


def delivery_window(path: str, box=PITCHER_BOX):
    """(start_s, end_s, peak_s) of the strongest 1.2-second motion burst in the pitcher box."""
    en, fps = motion_energy(path, box)
    sm = np.convolve(en, np.ones(5) / 5, mode="same")
    win = int(1.2 * fps)
    sums = np.convolve(sm, np.ones(win), mode="valid")
    i = int(np.argmax(sums))
    pk = i + int(np.argmax(sm[i:i + win]))
    return i / fps, (i + win) / fps, pk / fps


def candidates(path: str, t0: float, t1: float, roi=BALL_ROI):
    c = cv2.VideoCapture(path)
    fps = c.get(cv2.CAP_PROP_FPS)
    f0, f1 = max(0, int(t0 * fps) - STATIC_GAP), int(t1 * fps) + STATIC_GAP
    c.set(cv2.CAP_PROP_POS_FRAMES, f0)
    frames = []
    for _ in range(f1 - f0 + 1):
        ok, f = c.read()
        if not ok:
            break
        frames.append(f)
    masks = read_gray_white(frames)
    k = np.ones((11, 11), np.uint8)
    x0, y0, x1, y1 = roi
    out = {}
    for i in range(STATIC_GAP, len(frames) - STATIC_GAP):
        m = masks[i].copy()
        for j in (i - STATIC_GAP, i + STATIC_GAP):
            m = m & (1 - cv2.dilate(masks[j], k))
        sub = m[y0:y1, x0:x1]
        n, lab, st, cen = cv2.connectedComponentsWithStats(sub, connectivity=8)
        cs = []
        for q in range(1, n):
            a, w, h = st[q, cv2.CC_STAT_AREA], st[q, cv2.CC_STAT_WIDTH], st[q, cv2.CC_STAT_HEIGHT]
            if AREA[0] <= a <= AREA[1] and w <= 22 and h <= 22 and 0.4 <= w / max(h, 1) <= 2.5:
                cs.append((float(cen[q][0] + x0), float(cen[q][1] + y0), int(a)))
        out[f0 + i] = cs
    return out, fps


def link(cands: dict, minlen=MIN_TRACK, max_gap=5):
    """Tracks that fall steadily toward the plate. Net poles hide the ball for a few frames, so gaps up to max_gap frames are bridged
    using constant-velocity prediction. The first step of a track must move down (the ball leaves the hand heading to the plate)."""
    frames = sorted(cands)
    tracks = []
    for f in frames:
        for c in cands[f]:
            tr = [(f, c)]
            vel = None
            while True:
                lf, lc = tr[-1]
                best = None
                for gap in range(1, max_gap + 1):
                    for d in cands.get(lf + gap, []):
                        dx, dy = d[0] - lc[0], d[1] - lc[1]
                        if vel is None:
                            if gap > 2 or not (2.5 * gap <= dy <= 30 * gap) or abs(dx) > 8 * gap:
                                continue
                            dist = abs(dx) + abs(dy - 7 * gap) * 0.3
                            lim = 1e9
                        else:
                            dist = float(np.hypot(dx - vel[0] * gap, dy - vel[1] * gap))
                            lim = 7 + 2.5 * gap
                        if dist < lim and (best is None or dist < best[0]):
                            best = (dist, lf + gap, d)
                    if best:
                        break
                if not best:
                    break
                _, nf, d = best
                vel = ((d[0] - lc[0]) / (nf - lf), (d[1] - lc[1]) / (nf - lf))
                tr.append((nf, d))
            if len(tr) >= minlen:
                tracks.append(tr)
    tracks.sort(key=lambda t: (-len(t), t[0][0]))
    return tracks


def extend_back(track, cands: dict, tol=5.0, max_back=3):
    """Walk the line fitted to the first points of the track backward while candidates still sit on it. Returns the earliest on-line frame."""
    pts = track[: min(len(track), 6)]
    fr = np.array([f for f, _ in pts], float)
    ys = np.array([c[1] for _, c in pts]); xs = np.array([c[0] for _, c in pts])
    by = np.polyfit(fr, ys, 1); bx = np.polyfit(fr, xs, 1)
    first = track[0][0]
    f = first - 1
    miss = 0
    while miss <= 0 and f > first - max_back - 1:
        py, px = np.polyval(by, f), np.polyval(bx, f)
        hit = [d for d in cands.get(f, []) if abs(d[1] - py) <= tol and abs(d[0] - px) <= tol]
        if hit:
            first = f
        else:
            miss += 1
        f -= 1
    return first


def plausible(t) -> bool:
    """A real pitch track starts near the release point, falls at a steady rate, and stays in a narrow column."""
    ys = np.array([c[1] for _, c in t]); xs = np.array([c[0] for _, c in t]); fs = np.array([f for f, _ in t], float)
    if not (PITCHER_BOX[1] <= ys[0] <= PITCHER_BOX[1] + 160 and PITCHER_BOX[0] <= xs[0] <= PITCHER_BOX[2]):
        return False
    vy = np.polyfit(fs, ys, 1)[0]
    vx = np.polyfit(fs, xs, 1)[0]
    resid = float(np.abs(ys - np.polyval(np.polyfit(fs, ys, 1), fs)).max())
    return 3.5 <= vy <= 14 and abs(vx) <= 3.0 and resid <= 6.0


def find_release(path: str):
    """Returns dict(release_s, first_frame, fps, track) or None. release_s = first ball frame (lag is applied by the caller)."""
    s, e, pk = delivery_window(path)
    cands, fps = candidates(path, s, e + 0.8)
    # the ball leaves the hand at the arm snap, which is the motion peak in the pitcher box: accept tracks starting from 0.15 s before to 0.30 s after it
    tr = [t for t in link(cands) if plausible(t) and pk - 0.15 <= t[0][0] / fps <= pk + 0.30]
    if not tr:
        return None
    t = tr[0]
    first = extend_back(t, cands)
    xs = [c[0] for _, c in t]
    ys = [c[1] for _, c in t]
    return dict(first_frame=first, first_s=first / fps, track_start=t[0][0], last_frame=t[-1][0], length=len(t), fps=fps, window=(s, e, pk),
                start_xy=(round(xs[0]), round(ys[0])), end_xy=(round(xs[-1]), round(ys[-1])), track=[(f, round(c[0], 1), round(c[1], 1)) for f, c in t])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    a = ap.parse_args(argv)
    for p in a.clips:
        r = find_release(p)
        if r is None:
            print(p, "no ball track found")
            continue
        print(json.dumps({k: v for k, v in r.items() if k != "track"}), pathlib.Path(p).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def cut_package(path: str, workdir: str, offset: float = 0.150, lead: float = 1.6, tail: float = 1.2, crop_bottom: float = 0.0) -> dict:
    """Two files per pitch from video alone: pre ends `offset` s after the ball leaves the hand (no audio), reveal runs on from there."""
    import subprocess
    from .videocut import _ffmpeg
    r = find_release(path)
    if r is None:
        return dict(clip=pathlib.Path(path).name, status="release not found")
    fps = r["fps"]
    release = r["first_frame"] / fps
    start, pause = max(0.0, release - lead), release + offset
    w = pathlib.Path(workdir)
    w.mkdir(parents=True, exist_ok=True)
    stem = pathlib.Path(path).stem
    pre, rev = w / f"{stem}_pre.mp4", w / f"{stem}_reveal.mp4"
    vf = ["-vf", f"crop=iw:trunc(ih*{1 - crop_bottom}/2)*2:0:0"] if crop_bottom else []
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", path, "-ss", f"{start:.3f}", "-to", f"{pause:.3f}", "-an", *vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(pre)], check=True)
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", path, "-ss", f"{pause:.3f}", "-to", f"{release + tail + 0.6:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(rev)], check=True)
    return dict(clip=pathlib.Path(path).name, status="ok", release_frame=r["first_frame"], release_s=round(release, 3), pause_s=round(pause, 3), start_s=round(start, 3),
                offset=offset, release_source="video (ball track)", pre_file=pre.name, reveal_file=rev.name)
