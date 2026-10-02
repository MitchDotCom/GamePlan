"""Whole plate-appearance value of an approach (plan WS3).

A pitch-level swing-versus-take delta uses the league count table as the future. To compare approaches (value-max, contact, ...) the
future has to follow the approach. This does backward induction over the 12 counts for a menu of pitches per count:

  item k in count (b, s):  weight m_k (sums to 1), p_swing_k (the approach), whiff_k, foul_k, xw_k (xwOBA on contact), p_cs_k (called strike if taken)
  swing value = whiff * V(strike) + foul * V(foul) + (1 - whiff - foul) * xw
  take value  = p_cs * V(strike) + (1 - p_cs) * V(ball)
  V(b, s)     = sum_k m_k * (p_swing_k * swing + (1 - p_swing_k) * take)
Strike three is a strikeout (0), ball four a walk. A foul with two strikes stays in the count, solved as V = A / (1 - f).

Identity check (league): with the league's real pitches, real swing rates and the league model's outcome predictions, V must reproduce
the packaged count table (count_values_2025.json). Tolerance 0.15 relative, same as scorecard criterion 1.

    python -m gameplan.pa_value --league data/league --n 4000"""
from __future__ import annotations

import argparse
import glob
import pathlib
import random

import numpy as np

from .decision import DEFAULT, p_called_strike
from .savant import parse_swings
from .shape import ContactModel, raw_swing

COUNTS = [(b, s) for s in (2, 1, 0) for b in (3, 2, 1, 0)]      # evaluation order: every continuation is known (s=2 self-loops solved)


def solve(menus: dict, walk: float = DEFAULT.walk, k_value: float = DEFAULT.strikeout) -> dict:
    """menus[(b, s)] = dict of equal-length arrays: m, ps, whiff, foul, xw, pcs. Returns {(b, s): V}."""
    V = {}
    for b, s in COUNTS:
        mu = menus[(b, s)]
        m, ps, wh, fo, xw, pc = (np.asarray(mu[k], float) for k in ("m", "ps", "whiff", "foul", "xw", "pcs"))
        v_strike = k_value if s + 1 >= 3 else V[(b, s + 1)]
        v_ball = walk if b + 1 >= 4 else V[(b + 1, s)]
        bip = np.maximum(1.0 - wh - fo, 0.0)
        take = pc * v_strike + (1 - pc) * v_ball
        a = m * (ps * (wh * v_strike + bip * xw) + (1 - ps) * take)        # everything except the foul continuation
        f = float((m * ps * fo).sum())
        if s >= 2:
            V[(b, s)] = float(a.sum() / (1 - f))
        else:
            V[(b, s)] = float(a.sum() + f * V[(b, s + 1)])
    return V


def league_menus(rows, model: ContactModel, n: int, seed: int = 5) -> dict:
    """Per count: n real pitches (swings and takes) with the league model's predictions and the swing that actually happened."""
    rng = random.Random(seed)
    by = {c: [] for c in COUNTS}
    for r in rows:
        if r.balls <= 3 and r.strikes <= 2 and r.x_away is not None and r.z is not None and raw_swing(r, "shapecount") is not None:
            by[(r.balls, r.strikes)].append(r)
    out = {}
    for c, rs in by.items():
        rs = rng.sample(rs, min(n, len(rs)))
        Q = np.array([raw_swing(r, "shapecount") for r in rs], float)
        lg, _ = model.predict_pair(Q)
        out[c] = {"m": np.full(len(rs), 1.0 / len(rs)), "ps": np.array([float(r.swing) for r in rs]),
                  "whiff": lg["whiff"], "foul": lg["foul"], "xw": lg["xw"],
                  "pcs": np.array([p_called_strike(r.x_away, r.z, r.sz_bot or 1.5, r.sz_top or 3.5) for r in rs])}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--n", type=int, default=4000)
    a = ap.parse_args(argv)
    rows = []
    for f in sorted(glob.glob(str(pathlib.Path(a.league) / "*.csv"))):
        rows += parse_swings(open(f, encoding="utf-8-sig").read(), include_takes=True)
    sw = [r for r in rows if r.swing and r.date < "2025-07-01"]
    model = ContactModel([], sw, mode="shapecount")
    held = [r for r in rows if r.date >= "2025-07-01"]
    V = solve(league_menus(held, model, a.n))
    print(f"{'count':6s} {'DP value':>9s} {'table':>8s} {'rel err':>8s}")
    worst = 0.0
    for c in sorted(V, key=lambda c: (c[1], c[0])):
        t = DEFAULT.table[c]
        e = abs(V[c] - t) / t
        worst = max(worst, e)
        print(f"{c[0]}-{c[1]:<4d} {V[c]:9.4f} {t:8.4f} {e:8.3f}")
    print(f"max relative error {worst:.3f}  (tolerance 0.15)  {'PASS' if worst <= 0.15 else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
