"""Does a hitter-level (global) term help? Two-level shrinkage vs the current local-only shrinkage.

The published approach to small samples (empirical Bayes; Carleton stabilization) shrinks a hitter's
overall rate toward the league before anything else. The current ContactModel has no such term: each
location/shape neighbourhood is shrunk to the league on its own. This adds a hitter-level offset to the
league prior (offset = sum of residuals / (n + k_global)) and compares skill at small N.

    python -m gameplan.study_hier --batters data/b3
"""
from __future__ import annotations

import argparse

import numpy as np

from .shape import ContactModel
from .study import _boot, _fmt
from .validate_mlb import load_batters

CUT = "2025-07-01"


def _err(p, y_w, bip, y_x):
    return (float(((p["whiff"] - y_w) ** 2).sum()), float(len(y_w)),
            float(((p["xw"] - y_x)[bip] ** 2).sum()), float(bip.sum()))


def run(sw, lm, n, kgs, cut=CUT, min_train=400, min_test=150):
    per = {}
    for b, rows in sw.items():
        all_train = [s for s in rows if s.date < cut]
        test = [s for s in rows if s.date >= cut]
        if len(all_train) < min_train or len(test) < min_test:
            continue
        train = all_train[:n]
        Qt, mask = lm.query_swings(test)
        test = [s for s, k in zip(test, mask) if k]
        y_w = np.array([s.whiff for s in test], float)
        bip = np.array([s.xwoba is not None for s in test])
        y_x = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in test], float)
        Qtr, mtr = lm.query_swings(train)
        tr = [s for s, k in zip(train, mtr) if k]
        m = ContactModel.for_hitter(tr, lm, k_global_whiff=1e12, k_global_xw=1e12)   # term off = the pre-audit model
        acc = {}
        lg, hit = m.predict_pair(Qt)
        acc["base"] = _err(lg, y_w, bip, y_x)
        acc["current (local only)"] = _err(hit, y_w, bip, y_x)
        Qs = Qt / m.bw
        pr_tr = lm.predict(Qtr, use_hitter=False)
        yw_tr = np.array([s.whiff for s in tr], float)
        bip_tr = np.array([s.xwoba is not None for s in tr])
        yx_tr = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in tr], float)
        for kg in kgs:
            dw = (yw_tr - pr_tr["whiff"]).sum() / (len(tr) + kg)
            dx = ((yx_tr - pr_tr["xw"])[bip_tr].sum() / (bip_tr.sum() + kg * 0.4)) if bip_tr.sum() else 0.0
            out = {}
            for t, d in (("whiff", dw), ("xw", dx), ("foul", 0.0), ("su", 0.0)):
                ls, lw = m._l[t].sums(Qs)
                prior = (ls + m.m * m._g[t]) / (lw + m.m) + d
                hs, hw = m._h[t].sums(Qs)
                out[t] = (hs + m.k[t] * prior) / (hw + m.k[t])
            acc[f"+ hitter-level term, k_global={kg}"] = _err(out, y_w, bip, y_x)
        per[b] = acc
    names = [k for k in next(iter(per.values())) if k != "base"]
    print(f"N = {n} swings, {len(per)} hitters")
    for ti, tn in enumerate(["whiff Brier", "xwOBAcon MSE"]):
        print(f"  {tn}: skill vs league-only")
        for v in names:
            st = lambda vals, v=v, ti=ti: 1 - sum(x[v][2 * ti] for x in vals) / sum(x["base"][2 * ti] for x in vals)
            print(f"    {v:<42} {_fmt(_boot(per, st, 200))}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batters", required=True)
    ap.add_argument("--ns", default="50,100,200,400")
    ap.add_argument("--kgs", default="50,150,400")
    a = ap.parse_args(argv)
    b = load_batters(a.batters, takes=False)
    sw = {h: sorted([s for s in r if s.swing], key=lambda s: s.date) for h, r in b.items()}
    league = [s for r in sw.values() for s in r if s.date < CUT]
    lm = ContactModel([], league, mode="shape")
    for n in map(int, a.ns.split(",")):
        run(sw, lm, n, tuple(map(int, a.kgs.split(","))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
