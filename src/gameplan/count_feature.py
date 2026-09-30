"""Count as a model feature (mode "shapecount") versus count as a correction added afterwards.

Pre-registered before running:
  * Selection: count bandwidths (balls, strikes) from GRID_COUNT_BW chosen on time-blocked validation
    (May, June, July 2025), pooled whiff Brier plus xwOBAcon MSE relative to the default, same blocks as tune.py.
  * Final test used once: fit before 2025-08-01, score from 2025-08-01, hitters with enough swings.
    Compared: A = shape (no count), B = shapecount (chosen bandwidths).
  * Adopt B for a target only if B - A skill has a hitter-cluster bootstrap interval above 0.
  * Calibration by balls and strikes (C1) and separation S (V5) reported for A and B on the same period.
    B is only worth using if its calibration gaps shrink without new significant gaps appearing.

    python -m gameplan.count_feature --b25 data/league --pitchers data/league
"""
from __future__ import annotations

import argparse

import numpy as np

from .shape import ContactModel
from .study import _boot, _fmt
from .tune import BLOCKS, FINAL_START, MIN_TEST, MIN_TRAIN, _with_labels
from .validate_mlb import _frames, load_batters, load_start_keys, v5_separation
from .zone import CalledStrikeModel

GRID_COUNT_BW = [(b, s) for b in (1.0, 2.0, 4.0) for s in (0.5, 1.0, 2.0)]
DEFAULT_CB = (2.0, 1.0)


def _errors(sw_by_h, train_end, test_start, test_end, mode, cb=None, bw=1.0):
    league = [s for r in sw_by_h.values() for s in r if s.date < train_end]
    lm = ContactModel([], league, mode=mode, bw_scale=bw, count_bw=cb)
    out = {}
    for h, rows in sw_by_h.items():
        tr = [s for s in rows if s.date < train_end]
        te = [s for s in rows if test_start <= s.date < test_end]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        Q, mask = lm.query_swings(te)
        te = [s for s, k in zip(te, mask) if k]
        if not te:
            continue
        m = ContactModel.for_hitter(tr, lm)
        p = m.predict(Q, use_hitter=True)
        yw = np.array([s.whiff for s in te], float)
        bip = np.array([s.xwoba is not None for s in te])
        yx = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in te], float)
        out[h] = (float(((p["whiff"] - yw) ** 2).sum()), float(len(yw)),
                  float(((p["xw"] - yx)[bip] ** 2).sum()), float(bip.sum()))
    return out


def _baseline(sw_by_h, train_end, test_start):
    league = [s for r in sw_by_h.values() for s in r if s.date < train_end]
    lm = ContactModel([], league, mode="type")
    out = {}
    for h, rows in sw_by_h.items():
        te = [s for s in rows if s.date >= test_start]
        tr = [s for s in rows if s.date < train_end]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        Q, mask = lm.query_swings(te)
        te = [s for s, k in zip(te, mask) if k]
        p = lm.predict(Q, use_hitter=False)
        yw = np.array([s.whiff for s in te], float)
        bip = np.array([s.xwoba is not None for s in te])
        yx = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in te], float)
        out[h] = (float(((p["whiff"] - yw) ** 2).sum()), float(len(yw)),
                  float(((p["xw"] - yx)[bip] ** 2).sum()), float(bip.sum()))
    return out


def select(sw_by_h):
    print("\n== Selection: count bandwidths (balls, strikes), time-blocked validation, pooled error")
    ref = np.zeros(4)
    for start, end in BLOCKS:
        for v in _errors(sw_by_h, start, start, end, "shape").values():
            ref += v
    print(f"  no count feature: whiff {ref[0] / ref[1]:.5f}  xw {ref[2] / ref[3]:.5f}")
    table = {}
    for cb in GRID_COUNT_BW:
        tot = np.zeros(4)
        for start, end in BLOCKS:
            for v in _errors(sw_by_h, start, start, end, "shapecount", cb).values():
                tot += v
        table[cb] = (tot[0] / tot[1], tot[2] / tot[3])
        print(f"  count bw balls {cb[0]}, strikes {cb[1]}: whiff {table[cb][0]:.5f}  xw {table[cb][1]:.5f}")
    # one choice for both targets: lowest sum of the two errors relative to the no-count reference
    score = lambda cb: table[cb][0] / (ref[0] / ref[1]) + table[cb][1] / (ref[2] / ref[3])
    best = min(table, key=score)
    print(f"  chosen: balls {best[0]}, strikes {best[1]}")
    return best


def final_test(sw_by_h, cb):
    print(f"\n== Final test (used once): fit before {FINAL_START}, score from {FINAL_START}")
    base = _baseline(sw_by_h, FINAL_START, FINAL_START)
    a = _errors(sw_by_h, FINAL_START, FINAL_START, "9999", "shape")
    b = _errors(sw_by_h, FINAL_START, FINAL_START, "9999", "shapecount", cb)
    hs = sorted(set(base) & set(a) & set(b))
    per = {h: {"base": base[h], "a": a[h], "b": b[h]} for h in hs}
    for ti, tname in ((0, "whiff Brier"), (1, "xwOBAcon MSE")):
        skill = lambda v, k: 1 - sum(r[k][2 * ti] for r in v) / sum(r["base"][2 * ti] for r in v)
        da = _boot(per, lambda v: skill(v, "a"), 300)
        db = _boot(per, lambda v: skill(v, "b"), 300)
        diff = _boot(per, lambda v: skill(v, "b") - skill(v, "a"), 300)
        print(f"  {tname}: no count {_fmt(da)}   count feature {_fmt(db)}   B - A {_fmt(diff)}   ({len(hs)} hitters)")
        print(f"    adopt count feature for {tname.split()[0]}: {'YES' if diff[1] > 0 else 'NO (interval includes 0 or below)'}")


def calibration_and_separation(b25, pitchers, cb):
    from .audit_checks import c1_calibration_by_segment
    start_keys = load_start_keys(pitchers)
    zm = CalledStrikeModel([s for r in b25.values() for s in r if not s.swing and s.date < FINAL_START])
    league_train = [s for r in b25.values() for s in r if s.swing and s.date < FINAL_START]
    for label, mode, bw in (("A: no count feature", "shape", None), ("B: count feature", "shapecount", cb)):
        frames = _frames(b25, FINAL_START, start_keys, league_train, zm, mode=mode, count_bw=bw)
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
    sw = {h: sorted([s for s in r if s.swing], key=lambda s: s.date) for h, r in b25.items()}
    cb = select(sw)
    final_test(sw, cb)
    calibration_and_separation(b25, a.pitchers, cb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
