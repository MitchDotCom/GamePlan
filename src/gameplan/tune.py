"""Pre-registered tuning of kernel bandwidth and shrinkage per target, and the count recalibration test.

Procedure fixed before running (change it only with a dated note and rerun):
  * Selection uses time-blocked validation only: for each block (May, June, July 2025) fit on all swings
    before the block, score hitters (at least MIN_TRAIN prior swings, MIN_TEST in the block) on the block.
  * Grid: bandwidth multiplier x shrinkage multiplier (GRID_BW x GRID_K). One combination is chosen per
    target (whiff, xwOBAcon) by lowest pooled validation error; ties within 0.05% keep the default.
  * One final test, on swings from FINAL_START on, fit on everything before it. It is used once.
  * A tuned setting is adopted only if its final-test skill beats the default's with a hitter-cluster
    bootstrap interval that excludes zero.
  * Count recalibration (calibration.py) is fit on swings before FINAL_START and judged on the same final
    period: gaps by balls and strikes before and after, and separation (S) before and after.

    python -m gameplan.tune --b25 data/league --pitchers data/league
"""
from __future__ import annotations

import argparse

import numpy as np

from .calibration import CountCalibration
from .shape import ContactModel
from .study import _boot, _fmt
from .validate_mlb import _frames, load_batters, load_start_keys, v5_separation
from .zone import CalledStrikeModel

GRID_BW = (0.75, 1.0, 1.5, 2.0, 3.0)
GRID_K = (0.25, 0.5, 1.0, 2.0)
BLOCKS = (("2025-05-01", "2025-06-01"), ("2025-06-01", "2025-07-01"), ("2025-07-01", "2025-08-01"))
FINAL_START = "2025-08-01"
MIN_TRAIN, MIN_TEST = 150, 30
TIE = 0.0005


def _errors(sw_by_h, train_end, test_start, test_end, bw, ks):
    """Per-hitter (whiff SSE, n, xw SSE, n_bip) for a shape-hitter model, one (bandwidth, k) combination."""
    league = [s for r in sw_by_h.values() for s in r if s.date < train_end]
    lm = ContactModel([], league, mode="shape", bw_scale=bw)
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
        m = ContactModel.for_hitter(tr, lm, k_whiff=25 * ks, k_xw=12 * ks, k_su=12 * ks)
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
    print("\n== Selection: time-blocked validation (May, June, July), pooled error per combination")
    table = {}
    for bw in GRID_BW:
        for ks in GRID_K:
            tot = np.zeros(4)
            for start, end in BLOCKS:
                for v in _errors(sw_by_h, start, start, end, bw, ks).values():
                    tot += v
            table[(bw, ks)] = (tot[0] / tot[1], tot[2] / tot[3])
        print(f"  bandwidth x{bw}: " + "  ".join(f"k x{ks}: whiff {table[(bw, ks)][0]:.5f} xw {table[(bw, ks)][1]:.5f}" for ks in GRID_K))
    default = table[(1.0, 1.0)]
    best_w = min(table, key=lambda c: table[c][0])
    best_x = min(table, key=lambda c: table[c][1])
    # keep the default unless the winner is clearly better
    if default[0] - table[best_w][0] < TIE * default[0]:
        best_w = (1.0, 1.0)
    if default[1] - table[best_x][1] < TIE * default[1]:
        best_x = (1.0, 1.0)
    print(f"  default: whiff {default[0]:.5f}, xw {default[1]:.5f}")
    print(f"  chosen whiff: bandwidth x{best_w[0]}, k x{best_w[1]} ({table[best_w][0]:.5f});  xwOBAcon: bandwidth x{best_x[0]}, k x{best_x[1]} ({table[best_x][1]:.5f})")
    return best_w, best_x


def final_test(sw_by_h, best_w, best_x):
    print(f"\n== Final test (used once): fit before {FINAL_START}, score from {FINAL_START}")
    base = _baseline(sw_by_h, FINAL_START, FINAL_START)
    default = _errors(sw_by_h, FINAL_START, FINAL_START, "9999", 1.0, 1.0)
    w = _errors(sw_by_h, FINAL_START, FINAL_START, "9999", best_w[0], best_w[1])
    x = _errors(sw_by_h, FINAL_START, FINAL_START, "9999", best_x[0], best_x[1])
    hs = sorted(set(base) & set(default) & set(w) & set(x))
    per = {h: {"base": base[h], "default": default[h], "w": w[h], "x": x[h]} for h in hs}
    for ti, tname, key in ((0, "whiff Brier", "w"), (1, "xwOBAcon MSE", "x")):
        skill = lambda v, name: 1 - sum(r[name][2 * ti] for r in v) / sum(r["base"][2 * ti] for r in v)
        d = _boot(per, lambda v: skill(v, "default"), 300)
        t = _boot(per, lambda v: skill(v, key), 300)
        diff = _boot(per, lambda v: skill(v, key) - skill(v, "default"), 300)
        print(f"  {tname}: default skill {_fmt(d)}   tuned skill {_fmt(t)}   tuned - default {_fmt(diff)}   ({len(hs)} hitters)")
        print(f"    adopt tuned {tname.split()[0]} setting: {'YES' if diff[1] > 0 else 'NO (interval includes 0)'}")


def count_test(b25, pitchers, cutoff):
    print(f"\n== Count recalibration: fit before {cutoff}, judged from {cutoff} (vs starters)")
    from .audit_checks import c1_calibration_by_segment
    sw = {h: [s for s in r if s.swing] for h, r in b25.items()}
    cal = CountCalibration.fit({h: [s for s in r if s.date < cutoff] for h, r in sw.items()})
    print("  offsets (whiff, foul, xw) by (balls, strikes):")
    for c, o in sorted(cal.offsets.items()):
        print(f"    {c}: {o['whiff']:+.4f} {o['foul']:+.4f} {o['xw']:+.4f}")
    start_keys = load_start_keys(pitchers)
    zm = CalledStrikeModel([s for r in b25.values() for s in r if not s.swing and s.date < cutoff])
    league_train = [s for r in b25.values() for s in r if s.swing and s.date < cutoff]
    for label, c in (("BEFORE recalibration", None), ("AFTER recalibration", cal)):
        frames = _frames(b25, cutoff, start_keys, league_train, zm, count_cal=c)
        print(f"\n  --- {label}")
        c1_calibration_by_segment(b25, cutoff, start_keys, segments=("strikes", "balls"), frames=_with_labels(frames, b25, cutoff, start_keys))
        v5_separation(frames)
    return cal


def _with_labels(frames, events_by_hitter, cutoff, start_keys):
    """Attach the family / side / TTO labels the segment report expects."""
    from .audit_checks import FAMILY_OF, cap_tto
    for f in frames:
        rows = events_by_hitter[f["hitter"]]
        test = [s for s in rows if s.date >= cutoff and (s.game_pk, s.at_bat, s.pitch_no) in start_keys
                and s.x_away is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)]
        f["family"] = np.array([FAMILY_OF.get(s.pitch_type, "OTHER") for s in test])
        f["stand"] = np.array([s.stand for s in test])
        f["tto"] = np.array([cap_tto(s.tto) or 0 for s in test])
    return frames


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--parts", default="tune,count")
    ap.add_argument("--save-count-cal", default="src/gameplan/count_calibration_2025.json")
    a = ap.parse_args(argv)
    parts = set(a.parts.split(","))
    b25 = load_batters(a.b25)
    sw = {h: sorted([s for s in r if s.swing], key=lambda s: s.date) for h, r in b25.items()}
    if "tune" in parts:
        bw, bx = select(sw)
        final_test(sw, bw, bx)
    if "count" in parts:
        cal = count_test(b25, a.pitchers, FINAL_START)
        full = CountCalibration.fit(sw)
        open(a.save_count_cal, "w").write(full.to_json())
        print(f"\nsaved count calibration fit on the full season to {a.save_count_cal} (for use in plans; the test above used pre-{FINAL_START} data only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
