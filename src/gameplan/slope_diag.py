"""Diagnosis of the swing-EV calibration slope after the count feature was adopted (1.086, rule 0.95 to 1.05;
it was 1.023 before). DIAGNOSTIC ONLY: nothing here is adopted. Any setting that looks better is only a candidate
and needs its own pre-registered held-out test.

Same protocol as validate_mlb V2 / V5: fit before the cutoff, score on starters after it. Variants:
  A  shape (no count feature)                         the model before count was adopted
  B  shapecount (current default)
  C  shapecount, strikes count bandwidth 2.0          looser pooling across strike counts
  D  shapecount, bandwidth x1.5 and shrinkage x0.5    the setting the earlier tuning chose for whiff
  E  shape, bandwidth x1.5 and shrinkage x0.5         same setting without count
For each: swing-EV calibration slope with two-way interval, spread (SD) of predicted swing EV against SD of
realized, whiff and xwOBAcon skill-free MSE on the test swings, and the V5 individualization gap.

Also run on 2024 (independent season) at the same July 1 cutoff for A and B, to see whether the individualization
gap and the slope behave the same way there.

    python -m gameplan.slope_diag --b25 data/league --pitchers data/league --b24 data/league24 --p24 data/league24
"""
from __future__ import annotations

import argparse

import numpy as np

from .decision import evs_np
from .stats import interval, two_way_draws
from .study import _fmt
from .validate_mlb import _frames, load_batters, load_start_keys, v5_separation
from .zone import CalledStrikeModel

K_HALF = {"k_whiff": 12.5, "k_xw": 6.0, "k_su": 6.0}
VARIANTS = {
    "A shape (no count)": dict(mode="shape"),
    "B shapecount (default)": dict(mode="shapecount"),
    "C shapecount, strikes bw 2.0": dict(mode="shapecount", count_bw=(4.0, 2.0)),
    "D shapecount, bw x1.5, k x0.5": dict(mode="shapecount", league_kw={"bw_scale": 1.5}, hitter_kw=dict(K_HALF)),
    "E shape, bw x1.5, k x0.5": dict(mode="shape", league_kw={"bw_scale": 1.5}, hitter_kw=dict(K_HALF)),
}


def slope(frames):
    pred, real, hid, pit = [], [], [], []
    for k, f in enumerate(frames):
        sw, _ = evs_np(f["p"]["whiff"], f["p"]["foul"], f["p"]["xw"], f["p_cs"], f["balls"], f["strikes"])
        sel = f["swing"] & ~np.isnan(f["value"])
        pred.append(sw[sel]); real.append(f["value"][sel]); hid.append(np.full(sel.sum(), k)); pit.append(f["pitcher"][sel])
    pred, real, hid, pit = map(np.concatenate, (pred, real, hid, pit))
    _, pidx = np.unique(pit, return_inverse=True)

    def wslope(w):
        pm, rm = (w * pred).sum() / w.sum(), (w * real).sum() / w.sum()
        return float((w * (pred - pm) * (real - rm)).sum() / (w * (pred - pm) ** 2).sum())
    point, draws = two_way_draws(hid, pidx, wslope, 200)
    return interval(point, draws), float(pred.std()), float(real.std()), len(pred)


def run(events, start_keys, cutoff, label, variants):
    print(f"\n== {label}: fit before {cutoff}, score on starters after")
    zm = CalledStrikeModel([s for r in events.values() for s in r if not s.swing and s.date < cutoff])
    league_train = [s for r in events.values() for s in r if s.swing and s.date < cutoff]
    for name in variants:
        kw = VARIANTS[name]
        frames = _frames(events, cutoff, start_keys, league_train, zm, zone_balls=False, **kw)
        iv, sp, sr, n = slope(frames)
        print(f"\n  --- {name}")
        print(f"  swing EV slope {_fmt(iv)}   SD predicted {sp:.4f}   SD realized {sr:.4f}   ({n} swings)")
        v5_separation(frames)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--b24", required=True)
    ap.add_argument("--p24", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    a = ap.parse_args(argv)
    b25, b24 = load_batters(a.b25), load_batters(a.b24)
    run(b25, load_start_keys(a.pitchers), a.cutoff, "2025", list(VARIANTS))
    run(b24, load_start_keys(a.p24), "2024-07-01", "2024 (independent season)", ["A shape (no count)", "B shapecount (default)"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
