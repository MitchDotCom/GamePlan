"""Visual-only release finder for a fixed camera behind home plate (the 'low home' view). No audio, no tracking timestamp, no hand-set boxes.

Pipeline, all from pixels:
  1. Delivery: the strongest 1.2 s burst of motion in the upper part of the picture (the pitcher is far from the lens, the batter and umpire are lower).
  2. Pitcher: the largest connected region of that burst gives the pitcher's box and height. Everything below scales with that height.
  3. Ball track: small bright blobs that are not at the same place a few frames earlier or later (not static), linked frame to frame into a
     track that falls steadily, bridging the frames the net hides.
  4. Release = first frame of the ball track, which is also the top of the ball's path before it falls.
  5. Checks. Any failed check means no result (fail closed), with the reason recorded.

Developed on three Visalia clips. Accuracy on other clips is unknown until the acceptance test in docs/LOWHOME_ACCEPTANCE.md is run.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass, asdict

import cv2
import numpy as np


@dataclass(frozen=True)
class Config:
    white_min: int = 185            # min(B,G,R) at or above this counts as ball-white
    neutral_max: int = 60           # max-min channel spread allowed (rejects colored objects)
    static_gap: int = 4             # a blob is static if white sits there this many frames earlier or later
    min_track: int = 5              # frames
    max_gap: int = 5                # frames the net may hide the ball
    burst_seconds: float = 1.2
    burst_min_ratio: float = 1.3    # the delivery's peak motion in the pitcher box must exceed the clip's earlier 90th percentile by this factor
    window: tuple = (-0.15, 0.30)   # a ball track may start from this many seconds before to after the motion peak
    # pixel constants below are for a pitcher 165 px tall; they scale with the profile's scale
    area: tuple = (12, 220)
    vy: tuple = (3.5, 14.0)         # px per frame, steady fall
    vx_max: float = 3.0
    resid_max: float = 6.0
    first_dy: tuple = (2.5, 30.0)
    link_tol: float = 7.0


CFG = Config()
REF_HEIGHT = 165.0


@dataclass(frozen=True)
class CameraProfile:
    """Where the pitcher and the ball corridor are for one camera position. Learned by calibrate(), never typed by hand."""
    name: str
    scale: float                    # pitcher height in pixels / 165
    pitcher_box: tuple              # x0, y0, x1, y1 in full-frame pixels
    ball_roi: tuple                 # x0, y0, x1, y1
    size: tuple                     # frame width, height the profile was learned on
    calibrated_from: tuple = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(text: str) -> "CameraProfile":
        d = json.loads(text)
        for k in ("pitcher_box", "ball_roi", "size", "calibrated_from"):
            d[k] = tuple(d[k])
        return CameraProfile(**d)


def _white_mask(f, cfg):
    b, g, r = [f[:, :, i].astype(np.int16) for i in range(3)]
    mn, mx = np.minimum(np.minimum(b, g), r), np.maximum(np.maximum(b, g), r)
    return ((mn >= cfg.white_min) & ((mx - mn) <= cfg.neutral_max)).astype(np.uint8)


def candidates(path: str, t0: float, t1: float, roi, cfg: Config = CFG):
    """Moving ball-sized white blobs per frame inside roi: {frame: [(x, y, area, w, h)]}. Streams the video (small memory), keeps only 2*static_gap+1 masks."""
    from collections import deque
    c = cv2.VideoCapture(path)
    fps = c.get(cv2.CAP_PROP_FPS)
    gap = cfg.static_gap
    f0 = max(0, int(t0 * fps) - gap)
    f1 = int(t1 * fps) + gap
    c.set(cv2.CAP_PROP_POS_FRAMES, f0)
    x0, y0, x1, y1 = roi
    buf = deque(maxlen=2 * gap + 1)
    k = np.ones((11, 11), np.uint8)
    out = {}
    for f in range(f0, f1 + 1):
        ok, im = c.read()
        if not ok:
            break
        buf.append(_white_mask(im[y0:y1, x0:x1], cfg))
        if len(buf) < 2 * gap + 1:
            continue
        m = buf[gap] & (1 - cv2.dilate(buf[0], k)) & (1 - cv2.dilate(buf[-1], k))
        n, lab, st, cen = cv2.connectedComponentsWithStats(m, connectivity=8)
        cs = []
        for q in range(1, n):
            a, w, h = st[q, cv2.CC_STAT_AREA], st[q, cv2.CC_STAT_WIDTH], st[q, cv2.CC_STAT_HEIGHT]
            if 6 <= a <= 450 and w <= 40 and h <= 40 and 0.4 <= w / max(h, 1) <= 2.5:
                cs.append((float(cen[q][0] + x0), float(cen[q][1] + y0), int(a)))
        out[f - gap] = cs
    return out, fps


def _area_filter(cands: dict, s: float, cfg: Config):
    lo, hi = cfg.area[0] * s * s, cfg.area[1] * s * s
    return {f: [c for c in cs if lo <= c[2] <= hi] for f, cs in cands.items()}


def link(cands: dict, s: float, cfg: Config = CFG):
    """Tracks that fall steadily. The first step must move down; later steps follow constant-velocity prediction, bridging up to max_gap frames."""
    cands = _area_filter(cands, s, cfg)
    frames = sorted(cands)
    tracks = []
    for f in frames:
        for c in cands[f]:
            tr, vel = [(f, c)], None
            while True:
                lf, lc = tr[-1]
                best = None
                for gap in range(1, cfg.max_gap + 1):
                    for d in cands.get(lf + gap, []):
                        dx, dy = d[0] - lc[0], d[1] - lc[1]
                        if vel is None:
                            if gap > 2 or not (cfg.first_dy[0] * s * gap <= dy <= cfg.first_dy[1] * s * gap) or abs(dx) > 8 * s * gap:
                                continue
                            dist, lim = abs(dx) + abs(dy - 7 * s * gap) * 0.3, 1e9
                        else:
                            dist, lim = float(np.hypot(dx - vel[0] * gap, dy - vel[1] * gap)), (cfg.link_tol + 2.5 * gap) * s
                        if dist < lim and (best is None or dist < best[0]):
                            best = (dist, lf + gap, d)
                    if best:
                        break
                if not best:
                    break
                _, nf, d = best
                vel = ((d[0] - lc[0]) / (nf - lf), (d[1] - lc[1]) / (nf - lf))
                tr.append((nf, d))
            if len(tr) >= cfg.min_track:
                tracks.append(tr)
    tracks.sort(key=lambda t: (-len(t), t[0][0]))
    return tracks


def steady_fall(t, s: float, cfg: Config = CFG) -> bool:
    """The track falls at a steady rate in a narrow column."""
    ys = np.array([c[1] for _, c in t]); xs = np.array([c[0] for _, c in t]); fs = np.array([f for f, _ in t], float)
    fy, fx = np.polyfit(fs, ys, 1), np.polyfit(fs, xs, 1)
    resid = float(np.abs(ys - np.polyval(fy, fs)).max())
    return cfg.vy[0] * s <= fy[0] <= cfg.vy[1] * s and abs(fx[0]) <= cfg.vx_max * s and resid <= cfg.resid_max * s


def plausible(t, box, s: float, cfg: Config = CFG) -> bool:
    """A real pitch track also starts inside the pitcher's box."""
    x0, y0, x1, y1 = box
    sx, sy = t[0][1][0], t[0][1][1]
    return (x0 <= sx <= x1 and y0 <= sy <= y1) and steady_fall(t, s, cfg)


def extend_back(track, cands: dict, s: float, tol=5.0, max_back=3):
    """Walk the line fitted to the first points of the track backward while candidates still sit on it. Returns the earliest on-line frame."""
    pts = track[: min(len(track), 6)]
    fr = np.array([f for f, _ in pts], float)
    by = np.polyfit(fr, np.array([c[1] for _, c in pts]), 1)
    bx = np.polyfit(fr, np.array([c[0] for _, c in pts]), 1)
    first, f = track[0][0], track[0][0] - 1
    while f > track[0][0] - max_back - 1:
        py, px = np.polyval(by, f), np.polyval(bx, f)
        if any(abs(d[1] - py) <= tol * s and abs(d[0] - px) <= tol * s for d in cands.get(f, [])):
            first = f
            f -= 1
        else:
            break
    return first


def box_motion(path: str, box):
    """Mean absolute frame-to-frame change inside box, per frame."""
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


def delivery(path: str, profile: CameraProfile, cfg: Config = CFG):
    """(burst_start_s, burst_end_s, peak_s, ratio): the strongest burst of motion in the pitcher box, and how far its peak stands above the clip's earlier motion."""
    en, fps = box_motion(path, profile.pitcher_box)
    sm = np.convolve(en, np.ones(5) / 5, mode="same")
    win = max(5, int(cfg.burst_seconds * fps))
    sums = np.convolve(sm, np.ones(win), mode="valid")
    i = int(np.argmax(sums))
    pk = i + int(np.argmax(sm[i:i + win]))
    before = sm[: max(5, pk - int(1.0 * fps))]
    ratio = float(sm[pk] / max(np.percentile(before, 90), 1e-3))
    return i / fps, (i + win) / fps, pk / fps, ratio


def analyze(path: str, profile: CameraProfile, cfg: Config = CFG) -> dict:
    """Always returns a dict. status 'ok' carries the release; any other status carries the reason and no release (fail closed)."""
    rec = dict(clip=pathlib.Path(path).name, status="fail", reason=None, checks={}, profile=profile.name)
    cap = cv2.VideoCapture(path)
    if (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) != tuple(profile.size):
        rec["reason"] = f"frame size differs from the profile ({profile.size})"
        return rec
    s = profile.scale
    b0, b1, pk, ratio = delivery(path, profile, cfg)
    rec["checks"]["delivery_burst"] = ratio >= cfg.burst_min_ratio
    if not rec["checks"]["delivery_burst"]:
        rec["reason"] = f"no clear delivery in the pitcher box (peak only {ratio:.1f}x earlier motion)"
        return rec
    cands, fps = candidates(path, b0, b1 + 0.8, profile.ball_roi, cfg)
    good = [t for t in link(cands, s, cfg) if plausible(t, profile.pitcher_box, s, cfg) and pk + cfg.window[0] <= t[0][0] / fps <= pk + cfg.window[1]]
    rec["checks"]["ball_track_found"] = bool(good)
    if not good:
        rec["reason"] = "no plausible ball track near the delivery"
        return rec
    t = good[0]
    rivals = [u for u in good[1:] if abs(u[0][0] - t[0][0]) > 3 and len(u) >= max(cfg.min_track, len(t) - 1)]
    rec["checks"]["unambiguous"] = not rivals
    if rivals:
        rec["reason"] = f"{len(rivals) + 1} competing ball tracks"
        return rec
    first = extend_back(t, _area_filter(cands, s, cfg), s)
    rec.update(status="ok", reason=None, release_frame=int(first), release_s=round(first / fps, 4), fps=fps, track_len=len(t), peak_s=round(pk, 3), delivery_ratio=round(ratio, 2),
               start_xy=[round(t[0][1][0]), round(t[0][1][1])], track=[(f, round(c[0], 1), round(c[1], 1)) for f, c in t], pitcher_box=profile.pitcher_box,
               pitcher_height=round(s * REF_HEIGHT, 1))
    return rec


def calibrate(paths: list, name: str = "camera", cfg: Config = CFG, scales=(0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 2.0)) -> CameraProfile:
    """Learn a camera profile from clips of the same camera position: find falling balls anywhere in the upper frame, take the scale where
    the most clips have one, and place the pitcher box and ball corridor around where those balls start. Needs no typed numbers."""
    found = {s: [] for s in scales}
    size = None
    for p in paths:
        cap = cv2.VideoCapture(p)
        W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        size = size or (W, H)
        if (W, H) != size:
            raise ValueError("calibration clips must share one frame size")
        cands, fps = candidates(p, 0.0, cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps_of(cap), (0, 0, W, int(0.8 * H)), cfg)
        for s in scales:
            tr = [t for t in link(cands, s, cfg) if steady_fall(t, s, cfg) and len(t) >= cfg.min_track]
            if tr:
                found[s].append((p, tr[0][0][1][0], tr[0][0][1][1]))
    best = max(scales, key=lambda s: (len(found[s]), -abs(np.log(s))))
    pts = found[best]
    if not pts:
        raise ValueError("no falling ball found in the calibration clips")
    sx, sy = float(np.median([x for _, x, _ in pts])), float(np.median([y for _, _, y in pts]))
    H0 = best * REF_HEIGHT
    W, H = size
    box = (int(max(0, sx - 0.9 * H0)), int(max(0, sy - 0.7 * H0)), int(min(W, sx + 0.9 * H0)), int(min(H, sy + 1.0 * H0)))
    roi = (int(max(0, sx - 0.9 * H0)), int(max(0, sy - 0.7 * H0)), int(min(W, sx + 0.9 * H0)), int(min(H, sy + 2.6 * H0)))
    return CameraProfile(name=name, scale=best, pitcher_box=box, ball_roi=roi, size=size, calibrated_from=tuple(pathlib.Path(p).name for p in paths))


def fps_of(cap) -> float:
    return cap.get(cv2.CAP_PROP_FPS) or 60.0


def find_release(path: str, profile: CameraProfile):
    """Compatibility wrapper: dict with first_frame and fps, or None."""
    r = analyze(path, profile)
    if r["status"] != "ok":
        return None
    return dict(first_frame=r["release_frame"], first_s=r["release_s"], fps=r["fps"], track=r["track"], window=(0, 0, r["peak_s"]))


def audit_strip(path: str, rec: dict, out: pathlib.Path) -> pathlib.Path:
    """Eight crops around the detected release, ball track marked, so anyone can check the result at a glance."""
    c = cv2.VideoCapture(path)
    x0, y0, x1, y1 = rec["pitcher_box"]
    cx, hh = (x0 + x1) // 2, int(rec["pitcher_height"])
    bx0, by0, bx1, by1 = max(0, cx - hh), max(0, y0 - int(0.3 * hh)), cx + hh, y0 + int(1.2 * hh)
    pts = {f: (x, y) for f, x, y in rec["track"]}
    tiles = []
    for k in range(-3, 5):
        fr = rec["release_frame"] + k
        c.set(cv2.CAP_PROP_POS_FRAMES, fr)
        ok, im = c.read()
        if not ok:
            continue
        t = cv2.resize(im[by0:by1, bx0:bx1], (300, int(300 * (by1 - by0) / (bx1 - bx0))))
        if fr in pts:
            px, py = (pts[fr][0] - bx0) * 300 / (bx1 - bx0), (pts[fr][1] - by0) * 300 / (bx1 - bx0)
            cv2.circle(t, (int(px), int(py)), 14, (0, 255, 255), 1)
        cv2.putText(t, f"{k:+d}" + ("  RELEASE" if k == 0 else ""), (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        tiles.append(t)
    h = min(t.shape[0] for t in tiles)
    tiles = [t[:h] for t in tiles]
    while len(tiles) < 8:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:8])]))
    return out


def cut_package(path: str, profile: CameraProfile, workdir: str, offset: float = 0.100, lead: float = 1.6, tail: float = 1.2, crop_bottom: float = 0.0) -> dict:
    """Two files per pitch from video alone: pre ends `offset` s after the ball leaves the hand (no audio), reveal runs on from there."""
    import subprocess
    from .videocut import _ffmpeg
    r = analyze(path, profile)
    if r["status"] != "ok":
        return dict(clip=r["clip"], status="release not found", reason=r["reason"])
    release = r["release_frame"] / r["fps"]
    start, pause = max(0.0, release - lead), release + offset
    w = pathlib.Path(workdir)
    w.mkdir(parents=True, exist_ok=True)
    stem = pathlib.Path(path).stem
    pre, rev = w / f"{stem}_pre.mp4", w / f"{stem}_reveal.mp4"
    vf = ["-vf", f"crop=iw:trunc(ih*{1 - crop_bottom}/2)*2:0:0"] if crop_bottom else []
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", path, "-ss", f"{start:.3f}", "-to", f"{pause:.3f}", "-an", *vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(pre)], check=True)
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", path, "-ss", f"{pause:.3f}", "-to", f"{release + tail + 0.6:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(rev)], check=True)
    return dict(clip=r["clip"], status="ok", release_frame=r["release_frame"], release_s=round(release, 3), pause_s=round(pause, 3), start_s=round(start, 3),
                offset=offset, release_source="video (ball track)", pre_file=pre.name, reveal_file=rev.name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--calibrate", action="store_true", help="learn a camera profile from these clips and print it")
    ap.add_argument("--profile", default=None, help="profile JSON file")
    a = ap.parse_args(argv)
    if a.calibrate:
        print(calibrate(a.clips).to_json())
        return 0
    prof = CameraProfile.from_json(pathlib.Path(a.profile).read_text())
    for p in a.clips:
        r = analyze(p, prof)
        print(json.dumps({k: v for k, v in r.items() if k not in ("track", "config")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
