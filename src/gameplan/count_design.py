"""Fixed count design: a 3-ball-only called-strike surface and a 3-ball feature in the contact model.

Why: count_zone.py showed a full balls x strikes zone surface helped at 3 balls and hurt at 1 and 2
balls, so it failed overall. Count_feature.py showed the swing side is still off at 3 balls (hitters swing at 3
balls only on pitches they like). This run changes only the 3-ball case.

Pre-registered before running:
  * Design (fixed, not tuned on the test): zone surfaces by (3 balls, strikes), shrunk toward the strikes-only
    surface with m_balls = 25; every other count uses the strikes-only surface unchanged. Contact model
    "shapecount3" = shapecount plus an is-three-balls feature.
  * The only free parameter, the is-three-balls bandwidth, is chosen on 2025 May-July blocks from
    {0.5, 1.0, 2.0} by lowest pooled 3-ball swing error (whiff Brier + xwOBAcon MSE relative to shapecount).
  * Confirmation on 2024 (an independent season): fit before 2024-08-01, score from then on; a 2025 repeat is reported too.
      Z: 3-ball borderline take Brier, B - A, hitter-cluster bootstrap. Pass if the interval is below 0.
      W: 3-ball whiff skill, shapecount3 minus shapecount. Pass if the interval is above 0.
      X: 3-ball xwOBAcon skill, same. Pass if above 0.
      O: overall (all counts) whiff and xwOBAcon skill, shapecount3 minus shapecount. Pass if not below 0.
    Calibration by balls (C1) and separation (V5) for old and new design are printed for the record.
  * Each part passes or fails separately; only the parts that pass are adopted.

    python -m gameplan.count_design --b25 data/league --pitchers data/league --b24 data/league24 --p24 data/league24
"""
from __future__ import annotations

import argparse

import numpy as np

from .decision import p_called_strike
from .shape import ContactModel
from .study import _boot, _fmt
from .tune import BLOCKS, MIN_TEST, MIN_TRAIN, _with_labels
from .validate_mlb import _frames, load_batters, load_start_keys, v5_separation
from .zone import CalledStrikeModel

GRID_B3 = (0.5, 1.0, 2.0)
BASE_CB = (4.0, 1.0)


def _swing_errors(sw_by_h, train_end, test_start, test_end, mode, cb):
    """Per hitter: whiff / xw squared error overall and on 3-ball swings only (sse, n, sse_xw, n_bip) x 2."""
    league = [s for r in sw_by_h.values() for s in r if s.date < train_end]
    lm = ContactModel([], league, mode=mode, count_bw=cb)
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
        p = ContactModel.for_hitter(tr, lm).predict(Q, use_hitter=True)
        yw = np.array([s.whiff for s in te], float)
        bip = np.array([s.xwoba is not None for s in te])
        yx = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in te], float)
        b3 = np.array([s.balls >= 3 for s in te])
        ew, ex = (p["whiff"] - yw) ** 2, ((p["xw"] - yx) ** 2) * bip
        out[h] = {"w": (float(ew.sum()), float(len(yw))), "x": (float(ex.sum()), float(bip.sum())),
                  "w3": (float(ew[b3].sum()), float(b3.sum())), "x3": (float(ex[b3].sum()), float((b3 & bip).sum()))}
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
        b3 = np.array([s.balls >= 3 for s in te])
        ew, ex = (p["whiff"] - yw) ** 2, ((p["xw"] - yx) ** 2) * bip
        out[h] = {"w": (float(ew.sum()), float(len(yw))), "x": (float(ex.sum()), float(bip.sum())),
                  "w3": (float(ew[b3].sum()), float(b3.sum())), "x3": (float(ex[b3].sum()), float((b3 & bip).sum()))}
    return out


def select_b3(sw25):
    print("\n== Selection on 2025 May-July blocks: is-three-balls bandwidth (3-ball swings only, pooled error)")
    ref = {"w3": np.zeros(2), "x3": np.zeros(2)}
    for start, end in BLOCKS:
        for v in _swing_errors(sw25, start, start, end, "shapecount", BASE_CB).values():
            for k in ref:
                ref[k] += v[k]
    print(f"  shapecount (no 3-ball feature): whiff {ref['w3'][0] / ref['w3'][1]:.5f}  xw {ref['x3'][0] / ref['x3'][1]:.5f}")
    score = {}
    for b3 in GRID_B3:
        tot = {"w3": np.zeros(2), "x3": np.zeros(2)}
        for start, end in BLOCKS:
            for v in _swing_errors(sw25, start, start, end, "shapecount3", BASE_CB + (b3,)).values():
                for k in tot:
                    tot[k] += v[k]
        w, x = tot["w3"][0] / tot["w3"][1], tot["x3"][0] / tot["x3"][1]
        score[b3] = w / (ref["w3"][0] / ref["w3"][1]) + x / (ref["x3"][0] / ref["x3"][1])
        print(f"  is-3-balls bw {b3}: whiff {w:.5f}  xw {x:.5f}")
    best = min(score, key=score.get)
    print(f"  chosen: {best}")
    return best


def _skill_diff(per, key, a, b):
    sk = lambda v, name: 1 - sum(r[name][key][0] for r in v) / max(sum(r["base"][key][0] for r in v), 1e-12)
    return _boot(per, lambda v: sk(v, b) - sk(v, a), 300), _boot(per, lambda v: sk(v, b), 300), _boot(per, lambda v: sk(v, a), 300)


def swing_test(sw, cutoff, b3, label):
    print(f"\n== Swing side, {label}: fit before {cutoff}, score from {cutoff}")
    base = _baseline(sw, cutoff, cutoff)
    a = _swing_errors(sw, cutoff, cutoff, "9999", "shapecount", BASE_CB)
    b = _swing_errors(sw, cutoff, cutoff, "9999", "shapecount3", BASE_CB + (b3,))
    hs = sorted(set(base) & set(a) & set(b))
    per = {h: {"base": base[h], "a": a[h], "b": b[h]} for h in hs}
    print(f"  ({len(hs)} hitters)")
    for key, name, rule in (("w3", "W  3-ball whiff skill", "above"), ("x3", "X  3-ball xwOBAcon skill", "above"),
                            ("w", "O  overall whiff skill", "notbelow"), ("x", "O  overall xwOBAcon skill", "notbelow")):
        d, sb_, sa = _skill_diff(per, key, "a", "b")
        ok = d[1] > 0 if rule == "above" else d[1] >= 0
        print(f"  {name}: shapecount {_fmt(sa)}   shapecount3 {_fmt(sb_)}   diff {_fmt(d)}   -> {'PASS' if ok else 'FAIL'}")


def zone_test(events, cutoff, label):
    print(f"\n== Zone side, {label}: fit before {cutoff}, score from {cutoff}")
    zm = CalledStrikeModel([s for r in events.values() for s in r if not s.swing and s.date < cutoff])
    per = {}
    for h, rows in events.items():
        te = [s for s in rows if not s.swing and s.date >= cutoff and s.take_call in ("strike", "ball")
              and s.x_away is not None and s.balls >= 3]
        if not te:
            continue
        x = np.array([s.x_away for s in te]); z = np.array([s.z for s in te])
        sb = np.array([s.sz_bot or 1.5 for s in te]); st = np.array([s.sz_top or 3.5 for s in te])
        stk = np.array([s.strikes for s in te]); bal = np.array([s.balls for s in te])
        y = np.array([s.take_call == "strike" for s in te], float)
        stand = np.array([p_called_strike(a, b, c, d) for a, b, c, d in zip(x, z, sb, st)])
        edge = (stand > 0.05) & (stand < 0.95)
        ea = (zm.p(x, z, sb, st, strikes=stk) - y) ** 2
        eb = (zm.p(x, z, sb, st, strikes=stk, balls=bal) - y) ** 2
        if edge.any():
            per[h] = (float(ea[edge].sum()), float(eb[edge].sum()), float(edge.sum()))
    a = _boot(per, lambda v: sum(r[0] for r in v) / sum(r[2] for r in v), 300)
    b = _boot(per, lambda v: sum(r[1] for r in v) / sum(r[2] for r in v), 300)
    d = _boot(per, lambda v: (sum(r[1] for r in v) - sum(r[0] for r in v)) / sum(r[2] for r in v), 300)
    print(f"  Z  3-ball borderline Brier: strikes only {_fmt(a)}   3-ball surface {_fmt(b)}   B - A {_fmt(d)}   ({len(per)} hitters)"
          f"   -> {'PASS' if d[2] < 0 else 'FAIL'}")


def record(events, start_keys, cutoff, b3, label):
    from .audit_checks import c1_calibration_by_segment
    zm = CalledStrikeModel([s for r in events.values() for s in r if not s.swing and s.date < cutoff])
    league_train = [s for r in events.values() for s in r if s.swing and s.date < cutoff]
    for name, mode, cb, zb in (("old design (shapecount, strikes-only zone)", "shapecount", None, False),
                               ("new design (shapecount3, 3-ball zone)", "shapecount3", BASE_CB + (b3,), True)):
        frames = _frames(events, cutoff, start_keys, league_train, zm, mode=mode, count_bw=cb, zone_balls=zb)
        print(f"\n  --- {label}, {name}")
        c1_calibration_by_segment(events, cutoff, start_keys, segments=("balls",),
                                  frames=_with_labels(frames, events, cutoff, start_keys))
        v5_separation(frames)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--b24", required=True)
    ap.add_argument("--p24", required=True)
    a = ap.parse_args(argv)
    b25, b24 = load_batters(a.b25), load_batters(a.b24)
    sw25 = {h: sorted([s for s in r if s.swing], key=lambda s: s.date) for h, r in b25.items()}
    sw24 = {h: sorted([s for s in r if s.swing], key=lambda s: s.date) for h, r in b24.items()}
    b3 = select_b3(sw25)
    swing_test(sw24, "2024-08-01", b3, "2024 confirmation")
    zone_test(b24, "2024-08-01", "2024 confirmation")
    swing_test(sw25, "2025-08-01", b3, "2025 repeat (selection data, not independent)")
    zone_test(b25, "2025-08-01", "2025 repeat (not independent)")
    record(b24, load_start_keys(a.p24), "2024-08-01", b3, "2024")
    record(b25, load_start_keys(a.pitchers), "2025-08-01", b3, "2025")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
