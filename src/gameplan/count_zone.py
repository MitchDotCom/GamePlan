"""Does adding balls to the called-strike surface fix the 3-ball take gap?

Pre-registered before running:
  * Fit the zone surfaces on takes before 2025-08-01; judge on takes from then on.
  * A = surfaces by strikes (current). B = surfaces by balls and strikes, shrunk toward A (m_balls = 25,
    not tuned).
  * Test 1: Brier on held-out taken pitches that are borderline (stand-in strike probability within 0.05 to 0.95),
    B minus A, hitter-cluster bootstrap. Adopt B if the interval is below 0.
  * Test 2: take calibration by balls (realized minus predicted take value) and separation S with A and B
    plugged into the decision layer. B is worth keeping only if the 3-ball take gap shrinks and no new
    gap becomes significant.

    python -m gameplan.count_zone --b25 data/league --pitchers data/league
"""
from __future__ import annotations

import argparse

import numpy as np

from .decision import p_called_strike
from .study import _boot, _fmt
from .tune import FINAL_START, _with_labels
from .validate_mlb import _frames, load_batters, load_start_keys, v5_separation
from .zone import CalledStrikeModel


def test1(b25):
    print(f"\n== Test 1: called-strike Brier on held-out borderline takes (fit before {FINAL_START})")
    zm = CalledStrikeModel([s for r in b25.values() for s in r if not s.swing and s.date < FINAL_START])
    per, all_pairs = {}, []
    for h, rows in b25.items():
        te = [s for s in rows if not s.swing and s.date >= FINAL_START and s.take_call in ("strike", "ball")
              and s.x_away is not None]
        if not te:
            continue
        x = np.array([s.x_away for s in te]); z = np.array([s.z for s in te])
        sb = np.array([s.sz_bot or 1.5 for s in te]); st = np.array([s.sz_top or 3.5 for s in te])
        stk = np.array([s.strikes for s in te]); bal = np.array([s.balls for s in te])
        y = np.array([s.take_call == "strike" for s in te], float)
        stand = np.array([p_called_strike(a, b, c, d) for a, b, c, d in zip(x, z, sb, st)])
        edge = (stand > 0.05) & (stand < 0.95)
        pa = zm.p(x, z, sb, st, strikes=stk)
        pb = zm.p(x, z, sb, st, strikes=stk, balls=bal)
        ea, eb = (pa - y) ** 2, (pb - y) ** 2
        per[h] = {"a": float(ea[edge].sum()), "b": float(eb[edge].sum()), "n": float(edge.sum()),
                  **{f"a{k}": float(ea[edge & (bal == k)].sum()) for k in range(4)},
                  **{f"b{k}": float(eb[edge & (bal == k)].sum()) for k in range(4)},
                  **{f"n{k}": float((edge & (bal == k)).sum()) for k in range(4)}}
    per = {h: v for h, v in per.items() if v["n"] > 0}
    a = _boot(per, lambda v: sum(r["a"] for r in v) / sum(r["n"] for r in v), 300)
    b = _boot(per, lambda v: sum(r["b"] for r in v) / sum(r["n"] for r in v), 300)
    d = _boot(per, lambda v: (sum(r["b"] for r in v) - sum(r["a"] for r in v)) / sum(r["n"] for r in v), 300)
    print(f"  borderline Brier: strikes only {_fmt(a)}   balls x strikes {_fmt(b)}   B - A {_fmt(d)}   ({len(per)} hitters)")
    print(f"    adopt balls in the zone model: {'YES' if d[2] < 0 else 'NO (interval includes 0 or above)'}")
    for k in range(4):
        dk = _boot({h: v for h, v in per.items() if v[f"n{k}"] > 0},
                   lambda v, k=k: (sum(r[f"b{k}"] for r in v) - sum(r[f"a{k}"] for r in v)) / sum(r[f"n{k}"] for r in v), 200)
        print(f"    {k} balls: B - A {_fmt(dk)}")
    return zm


def test2(b25, pitchers):
    from .audit_checks import c1_calibration_by_segment
    start_keys = load_start_keys(pitchers)
    zm = CalledStrikeModel([s for r in b25.values() for s in r if not s.swing and s.date < FINAL_START])
    league_train = [s for r in b25.values() for s in r if s.swing and s.date < FINAL_START]
    for label, zb in (("A: zone by strikes", False), ("B: zone by balls and strikes", True)):
        frames = _frames(b25, FINAL_START, start_keys, league_train, zm, zone_balls=zb)
        print(f"\n  --- {label}")
        c1_calibration_by_segment(b25, FINAL_START, start_keys, segments=("strikes", "balls"),
                                  frames=_with_labels(frames, b25, FINAL_START, start_keys))
        v5_separation(frames)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    a = ap.parse_args(argv)
    b25 = load_batters(a.b25)
    test1(b25)
    test2(b25, a.pitchers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
