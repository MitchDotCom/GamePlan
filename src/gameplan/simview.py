"""A pitch drawn from its tracking, for levels and games that have data but no usable video (and for camera angles no video offers).

Statcast coordinates (feet): x is lateral, positive toward the catcher's right (first-base side); y is distance from the plate, 50 at release and 17/12 at the front of the plate;
z is height. The ball's position at time t after release is p(t) = p0 + v0 t + a t^2 / 2 with p0 = (x0, y0, z0), v0 = (vx0, vy0, vz0), a = (ax, ay, az).

A row becomes a drawn pitch only if every check below passes; otherwise it is rejected with the reason, never drawn from partial numbers:
  fields      all nine parameters, the plate location (px, pz) and the zone (sz_top, sz_bot) are finite numbers
  release     y0 is within 1 ft of 50 (the parameters are defined at that plane)
  zone time   the ball reaches the front of the plate 0.30 to 0.60 s after release, and that time equals the feed's own plateTimeSZDepth (when present) within 5 ms
  location    the path evaluated at that time reproduces the feed's px, pz within 0.02 ft (so the drawn pitch and the answer key can never disagree)
  speed       the speed from (vx0, vy0, vz0) is within 1.5 mph of start_speed (it differs by about 0.6 mph on real rows)
  monotone    y strictly falls from release to the plate (no bounce, no turnaround)

What this is not: a recording. It has no delivery, arm slot, spin appearance or lighting, so it cannot train what depends on those. Whether it trains recognition is untested.
"""
from __future__ import annotations

import math

FIELDS = ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")
Y_PLATE = 17 / 12
MPH = 0.681818


def _f(p: dict, k: str):
    try:
        x = float(p.get(k))
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def t_to_plane(par: dict, y: float = Y_PLATE):
    """Seconds after release when the ball reaches distance y from the plate, or None."""
    a, b, c = 0.5 * par["ay"], par["vy0"], par["y0"] - y
    if abs(a) < 1e-9:
        return None
    d = b * b - 4 * a * c
    if d < 0:
        return None
    ts = [t for t in ((-b - math.sqrt(d)) / (2 * a), (-b + math.sqrt(d)) / (2 * a)) if t > 0]
    return min(ts) if ts else None


def position(par: dict, t: float) -> tuple:
    return tuple(par[c + "0"] + par["v" + c + "0"] * t + 0.5 * par["a" + c] * t * t for c in ("x", "y", "z"))


def sim_params(p: dict) -> tuple:
    """-> (params dict or None, reason or None)."""
    par = {k: _f(p, k) for k in FIELDS}
    px, pz, top, bot, sp = (_f(p, k) for k in ("px", "pz", "sz_top", "sz_bot", "start_speed"))
    if None in par.values() or None in (px, pz, top, bot, sp):
        return None, "missing or non-numeric tracking fields"
    if abs(par["y0"] - 50) > 1:
        return None, f"release plane y0={par['y0']:.2f} is not near 50 ft"
    t = t_to_plane(par)
    if t is None or not 0.30 <= t <= 0.60:
        return None, f"zone time {t} outside 0.30 to 0.60 s"
    tz = _f(p, "plateTimeSZDepth")
    if tz is not None and abs(t - tz) > 0.005:
        return None, f"zone time {t:.4f} s disagrees with the feed's {tz:.4f} s"
    x, y, z = position(par, t)
    if abs(x - px) > 0.02 or abs(z - pz) > 0.02:
        return None, f"path crosses at ({x:.3f}, {z:.3f}) but the feed says ({px:.3f}, {pz:.3f})"
    speed = math.sqrt(par["vx0"] ** 2 + par["vy0"] ** 2 + par["vz0"] ** 2) * MPH
    if abs(speed - sp) > 1.5:
        return None, f"speed {speed:.1f} mph from the vector vs {sp:.1f} mph reported"
    if any(par["vy0"] + par["ay"] * s * t / 20 >= 0 for s in range(21)):
        return None, "ball is not moving toward the plate throughout"
    out = {k: round(v, 5) for k, v in par.items()}
    out.update(t_zone=round(t, 5), px=round(px, 4), pz=round(pz, 4), sz_top=round(top, 3), sz_bot=round(bot, 3), stand=p.get("stand"), p_throws=p.get("p_throws"))
    return out, None


def sim_cutter(p: dict, work=None, out=None):
    """app_content cutter for a drawn pitch: no file, release at 0, the parameters travel with the item. None when a check fails."""
    par, why = sim_params(p)
    return None if par is None else dict(release=0.0, sim=par)


def separation(pars_by_type: dict, t: float) -> dict:
    """How far apart two pitch types' mean positions are at time t after release, in feet, for each pair. A pitch-type question can only be answered from the path if these are not tiny;
    there is no validated threshold, so this is reported, not enforced."""
    mean = {k: tuple(sum(c) / len(v) for c in zip(*[position(q, t) for q in v])) for k, v in pars_by_type.items() if v}
    ks = sorted(mean)
    return {f"{a}-{b}": round(math.dist(mean[a], mean[b]), 3) for i, a in enumerate(ks) for b in ks[i + 1:]}
