"""Checks written to find where the model is wrong, not to confirm it works.

  C1  Calibration by segment. Overall calibration (validate_mlb V2) can hide a model that is right on
      average and wrong in the spots that matter. Predicted vs realized swing value and take value by
      strike count, ball count, pitch family, batter side and time through the order.
  C2  Hyperparameter sensitivity. Bandwidth scale, neighbour count and shrinkage strength were chosen
      by hand. If skill moves a lot when they change, the reported skill is partly luck of the setting.
  C3  Split-date sensitivity. Everything so far used one cutoff (2025-07-01).
  C4  Data-handling effects. Foul tips as whiffs, bunts excluded, balls in play without Savant xwOBA
      dropped. How much do the earlier results move?

    python -m gameplan.audit_checks --b25 data/b3 --pitchers data/p2 --tests 1,2,3,4
"""
from __future__ import annotations

import argparse
import glob
import pathlib

import numpy as np

from .coach import FAMILY_OF
from .decision import evs_np
from .savant import parse_swings
from .shape import ContactModel, cap_tto
from .study import _boot, _fmt, _read
from .validate_mlb import _frames, load_batters, load_start_keys
from .zone import CalledStrikeModel

CUTOFF = "2025-07-01"


# ------------------------------------------------------------------ C1

def _segment_frames(events_by_hitter, cutoff, start_keys):
    """Like validate_mlb._frames but also keeps segment labels per pitch."""
    league_train = [s for r in events_by_hitter.values() for s in r if s.swing and s.date < cutoff]
    zm = CalledStrikeModel([s for r in events_by_hitter.values() for s in r if not s.swing and s.date < cutoff])
    frames = _frames(events_by_hitter, cutoff, start_keys, league_train, zm)
    # _frames drops row objects; rebuild the same row selection to attach labels
    for f in frames:
        rows = events_by_hitter[f["hitter"]]
        test = [s for s in rows if s.date >= cutoff and (s.game_pk, s.at_bat, s.pitch_no) in start_keys
                and s.x_away is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)]
        f["family"] = np.array([FAMILY_OF.get(s.pitch_type, "OTHER") for s in test])
        f["stand"] = np.array([s.stand for s in test])
        f["tto"] = np.array([cap_tto(s.tto) or 0 for s in test])
    return frames


def c1_calibration_by_segment(events_by_hitter, cutoff, start_keys):
    print("\n== C1: calibration by segment (realized minus predicted value, wOBA scale; 0 = calibrated)")
    print("   Rows where the gap's 95% CI (by hitter) excludes 0 are marked *.")
    frames = _segment_frames(events_by_hitter, cutoff, start_keys)
    segs = {
        "strikes": lambda f: f["strikes"], "balls": lambda f: f["balls"], "pitch family": lambda f: f["family"],
        "batter side": lambda f: f["stand"], "time through order": lambda f: f["tto"],
    }
    for sname, get in segs.items():
        labels = sorted({v for f in frames for v in np.unique(get(f))}, key=str)
        print(f"  by {sname}:")
        for lab in labels:
            row = []
            for is_swing, name in ((True, "swing"), (False, "take")):
                per = {}
                for k, f in enumerate(frames):
                    sw, tk = evs_np(f["p"]["whiff"], f["p"]["foul"], f["p"]["xw"], f["p_cs"], f["balls"], f["strikes"])
                    sel = (f["swing"] == is_swing) & (get(f) == lab) & ~np.isnan(f["value"])
                    if sel.any():
                        per[k] = (float((f["value"][sel] - (sw if is_swing else tk)[sel]).sum()), int(sel.sum()))
                if not per:
                    row.append(f"{name}: n/a")
                    continue
                n = sum(v[1] for v in per.values())
                est, lo, hi = _boot(per, lambda vals: sum(v[0] for v in vals) / sum(v[1] for v in vals), 200)
                row.append(f"{name} {est:+.4f} [{lo:+.4f}, {hi:+.4f}]{'*' if lo > 0 or hi < 0 else ' '} n={n}")
            print(f"    {str(lab):<8} " + "   ".join(row))


# ------------------------------------------------------------------ C2 / C3 / C4

def _skill(sw_by_h, cutoff, bw_scale=1.0, K_hitter=80, K_league=400, k_scale=1.0, min_train=300, min_test=150):
    """Whiff / xwOBAcon skill of a shape-hitter model vs a type-league model, one setting."""
    league = [s for r in sw_by_h.values() for s in r if s.date < cutoff]
    kw = dict(bw_scale=bw_scale, K_hitter=K_hitter, K_league=K_league,
              k_whiff=25 * k_scale, k_xw=12 * k_scale, k_su=12 * k_scale)
    lm_shape = ContactModel([], league, mode="shape", **kw)
    lm_type = ContactModel([], league, mode="type", **kw)
    per = {}
    for b, rows in sw_by_h.items():
        train = [s for s in rows if s.date < cutoff]
        test = [s for s in rows if s.date >= cutoff]
        if len(train) < min_train or len(test) < min_test:
            continue
        Q, mask = lm_shape.query_swings(test)
        test = [s for s, k in zip(test, mask) if k]
        y_w = np.array([s.whiff for s in test], float)
        bip = np.array([s.xwoba is not None for s in test])
        y_x = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in test], float)

        def err(p):
            return (float(((p["whiff"] - y_w) ** 2).sum()), float(len(y_w)),
                    float(((p["xw"] - y_x)[bip] ** 2).sum()), float(bip.sum()))
        Qt, _ = lm_type.query_swings(test)
        m = ContactModel(train, [], mode="shape", **kw)
        m._l, m._g = lm_shape._l, lm_shape._g
        per[b] = {"base": err(lm_type.predict(Qt, use_hitter=False)), "hit": err(m.predict(Q, use_hitter=True))}
    out = []
    for ti in (0, 1):
        st = lambda vals, ti=ti: 1 - sum(x["hit"][2 * ti] for x in vals) / sum(x["base"][2 * ti] for x in vals)
        out.append(_boot(per, st, 150))
    return len(per), out


def _print_skill(label, res):
    n, (w, x) = res
    print(f"    {label:<44} whiff {_fmt(w)}   xwOBAcon {_fmt(x)}   ({n} hitters)")


def c2_hyperparameters(sw_by_h, cutoff):
    print("\n== C2: hyperparameter sensitivity (skill of shape-hitter vs league type model; default marked)")
    for scale in (0.5, 1.0, 2.0):
        _print_skill(f"kernel bandwidth x{scale}{' (default)' if scale == 1.0 else ''}", _skill(sw_by_h, cutoff, bw_scale=scale))
    for k in (40, 80, 160):
        _print_skill(f"hitter neighbours K={k}{' (default)' if k == 80 else ''}", _skill(sw_by_h, cutoff, K_hitter=k))
    for ks in (0.25, 0.5, 1.0, 2.0, 4.0):
        _print_skill(f"shrinkage strength x{ks}{' (default)' if ks == 1.0 else ''}", _skill(sw_by_h, cutoff, k_scale=ks))


def c3_split_dates(sw_by_h):
    print("\n== C3: split-date sensitivity")
    for cutoff in ("2025-05-15", "2025-06-15", "2025-07-01", "2025-08-01"):
        _print_skill(f"cutoff {cutoff}", _skill(sw_by_h, cutoff))


def c4_data_handling(b25_dir):
    print("\n== C4: data-handling effects on skill (same model, same cutoff)")
    variants = {
        "as before (foul tips = fouls, bunts in)": {"foul_tip_as_whiff": False, "exclude_bunts": False, "strict_xwoba": False},
        "foul tips as whiffs": {"foul_tip_as_whiff": True, "exclude_bunts": False, "strict_xwoba": False},
        "bunts excluded": {"foul_tip_as_whiff": False, "exclude_bunts": True, "strict_xwoba": False},
        "BIP without Savant xwOBA dropped": {"foul_tip_as_whiff": False, "exclude_bunts": False, "strict_xwoba": True},
        "all three fixes": {"foul_tip_as_whiff": True, "exclude_bunts": True, "strict_xwoba": True},
    }
    texts = list(_read(sorted(glob.glob(str(pathlib.Path(b25_dir) / "*.csv")))))
    for label, kw in variants.items():
        sw: dict = {}
        for t in texts:
            for s in parse_swings(t, **kw):
                sw.setdefault(s.batter, []).append(s)
        n_sw = sum(len(v) for v in sw.values())
        whiff = np.mean([s.whiff for v in sw.values() for s in v])
        print(f"  {label}: swings {n_sw}, whiff rate per swing {whiff:.4f}")
        _print_skill("   skill", _skill(sw, CUTOFF))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--tests", default="1,2,3,4")
    ap.add_argument("--cutoff", default=CUTOFF)
    a = ap.parse_args(argv)
    tests = set(a.tests.split(","))
    b25 = load_batters(a.b25)
    sw = {b: [s for s in r if s.swing] for b, r in b25.items()}
    if "1" in tests:
        c1_calibration_by_segment(b25, a.cutoff, load_start_keys(a.pitchers))
    if "2" in tests:
        c2_hyperparameters(sw, a.cutoff)
    if "3" in tests:
        c3_split_dates(sw)
    if "4" in tests:
        c4_data_handling(a.b25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
