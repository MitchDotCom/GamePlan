"""Low-data validation: what survives when a park has less tracking or a hitter has few swings?

Test 6  Feature ladder: location only -> +type -> +velo -> full shape, and no exit-velo / launch-angle
        (actual wOBA instead of xwOBA). How much skill does each rung buy?
Test 7  Learning curve: skill vs the number of a hitter's swings available (earliest N of his season),
        with different shrinkage strengths. When does hitter-specific beat league-only?
Test 8  Coach-report priors, mechanism check by simulation. Emulated reports carry a chosen
        correlation rho with the hitter's true tendency in 9 cells (pitch family x height). Shows the
        report accuracy needed to help at each N, and the harm from an uninformative report (rho = 0).
        This validates the mechanism, not any real coach's accuracy.

    python -m gameplan.study_lowdata --batters data/b2
"""
from __future__ import annotations

import argparse
import glob
import pathlib

import numpy as np

from .coach import FAMILY_OF, CoachProfile, CoachTag, vert_region
from .savant import SwingRow, parse_swings
from .shape import ContactModel
from .study import _boot, _fmt, _read

RNG = np.random.default_rng(3)


def _truth(test):
    y_w = np.array([s.whiff for s in test], float)
    bip = np.array([s.xwoba is not None for s in test], bool)
    y_x = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in test], float)
    return y_w, bip, y_x


def _sse(p, y_w, bip, y_x):
    return (float(((p["whiff"] - y_w) ** 2).sum()), float(len(y_w)),
            float(((p["xw"] - y_x)[bip] ** 2).sum()), float(bip.sum()))


def _skill_table(per_h, base, variants, title):
    print(title)
    for ti, tname in enumerate(["whiff Brier", "xwOBAcon MSE"]):
        print(f"  {tname}: skill vs {base} (1 - err/err_base; 95% CI by hitter)")
        for v in variants:
            def stat(vals, v=v, ti=ti):
                return 1.0 - sum(x[v][2 * ti] for x in vals) / sum(x[base][2 * ti] for x in vals)
            print(f"    {v:<38} {_fmt(_boot(per_h, stat))}")


def _split(rows, cutoff):
    return [s for s in rows if s.date < cutoff], [s for s in rows if s.date >= cutoff]


def test6(swings_by_hitter, cutoff, league_train):
    print("\n== Test 6: feature ladder (what each rung of tracking buys), scored on held-out swings")
    lm = {m: ContactModel([], league_train, mode=m) for m in ("loc", "type", "typevelo", "shape")}
    lm_woba = ContactModel([], league_train, mode="type", xw_attr="woba")
    per_h = {}
    for b, rows in swings_by_hitter.items():
        train, test = _split(rows, cutoff)
        if len(train) < 300 or len(test) < 150:
            continue
        _, mask = lm["shape"].query_swings(test)      # common rows: every rung can score them
        test = [s for s, k in zip(test, mask) if k]
        _, mk2 = lm["typevelo"].query_swings(test)
        test = [s for s, k in zip(test, mk2) if k]
        y_w, bip, y_x = _truth(test)
        acc = {}

        def run(name, mode, hitter, xw_attr="xwoba", league=None):
            m = ContactModel(train if hitter else [], [], mode=mode, xw_attr=xw_attr)
            src = league or lm[mode]
            m._l, m._g = src._l, src._g
            Q, _ = m.query_swings(test)
            lg, hit = m.predict_pair(Q)
            acc[name] = _sse(hit if hitter else lg, y_w, bip, y_x)

        run("A type, league only (baseline)", "type", False)
        run("B location only, hitter", "loc", True)
        run("C + pitch type, hitter", "type", True)
        run("D + velocity, hitter", "typevelo", True)
        run("E + full shape, hitter", "shape", True)
        run("F pitch type, hitter, no EV/LA (actual wOBA)", "type", True, "woba", lm_woba)
        per_h[b] = acc
    _skill_table(per_h, "A type, league only (baseline)", [v for v in next(iter(per_h.values()))
                                                           if not v.startswith("A")], "")
    print(f"  hitters scored: {len(per_h)}")


def test7(swings_by_hitter, cutoff, league_train, ns=(50, 100, 200, 400)):
    print("\n== Test 7: learning curve, hitter-specific skill vs number of his swings (earliest N of the season)")
    lm = {m: ContactModel([], league_train, mode=m) for m in ("type", "shape")}
    for n in ns:
        per_h = {}
        for b, rows in swings_by_hitter.items():
            train, test = _split(sorted(rows, key=lambda s: s.date), cutoff)
            if len(train) < max(ns) or len(test) < 150:
                continue
            train = train[:n]
            _, mask = lm["shape"].query_swings(test)
            t2 = [s for s, k in zip(test, mask) if k]
            y_w, bip, y_x = _truth(t2)
            acc = {}
            for name, mode, scale in (("type, k x1", "type", 1.0), ("type, k x2 (stiffer)", "type", 2.0),
                                      ("type, k x0.5 (looser)", "type", 0.5), ("shape, k x1", "shape", 1.0)):
                m = ContactModel(train, [], mode=mode, k_whiff=25 * scale, k_xw=12 * scale, k_su=12 * scale)
                m._l, m._g = lm[mode]._l, lm[mode]._g
                Q, _ = m.query_swings(t2)
                lg, hit = m.predict_pair(Q)
                acc[name] = _sse(hit, y_w, bip, y_x)
                if name == "type, k x1":
                    acc["base"] = _sse(lg, y_w, bip, y_x)
            per_h[b] = acc
        if per_h:
            _skill_table(per_h, "base", ["type, k x1", "type, k x2 (stiffer)", "type, k x0.5 (looser)", "shape, k x1"],
                         f" N = {n} swings ({len(per_h)} hitters with at least {max(ns)} training swings)")


def _family_vert(s):
    return FAMILY_OF.get(s.pitch_type, ""), vert_region(s.z)


def _true_dev(rows, league_rows):
    """Hitter minus league whiff rate and xwOBAcon in each (pitch family, height) cell."""
    def agg(rs):
        d: dict = {}
        for s in rs:
            k = _family_vert(s)
            a = d.setdefault(k, [0, 0, 0, 0.0])
            a[0] += 1
            a[1] += s.whiff
            if s.xwoba is not None:
                a[2] += 1
                a[3] += s.xwoba
        return d
    h, lg = agg(rows), agg(league_rows)
    out = {}
    for k, a in h.items():
        b = lg.get(k)
        if not b or a[0] < 30 or b[0] < 200 or not k[0]:
            continue
        dw = a[1] / a[0] - b[1] / b[0]
        dx = (a[3] / a[2] - b[3] / b[2]) if a[2] >= 15 and b[2] >= 50 else 0.0
        out[k] = (dw, dx)
    return out


def test8(swings_by_hitter, cutoff, league_train, ns=(50, 100, 200), rhos=(0.0, 0.3, 0.5, 0.7)):
    print("\n== Test 8: coach-report priors, mechanism by simulation (rho = correlation of report with true tendency)")
    all_swings = [s for rows in swings_by_hitter.values() for s in rows]
    lm = ContactModel([], league_train, mode="type")
    dev = {}
    for b, rows in swings_by_hitter.items():
        dev[b] = _true_dev(rows, [s for s in all_swings if s.batter != b][::7])
    sdw = float(np.std([v[0] for d in dev.values() for v in d.values()]))
    sdx = float(np.std([v[1] for d in dev.values() for v in d.values()]))
    for n in ns:
        per_h = {}
        for b, rows in swings_by_hitter.items():
            train, test = _split(sorted(rows, key=lambda s: s.date), cutoff)
            if len(train) < max(ns) or len(test) < 150 or not dev[b]:
                continue
            train = train[:n]
            y_w, bip, y_x = _truth(test)
            acc = {}
            for rho in [None] + list(rhos):
                m = ContactModel(train, [], mode="type")
                m._l, m._g = lm._l, lm._g
                Q, _ = m.query_swings(test)
                coach = None
                if rho is not None:
                    tags = []
                    for (fam, vert), (dw, dx) in dev[b].items():
                        e = RNG.standard_normal(2)
                        sw = rho * dw + np.sqrt(1 - rho ** 2) * sdw * e[0]
                        sx = rho * dx + np.sqrt(1 - rho ** 2) * sdx * e[1]
                        tags.append(CoachTag(family=fam, vert=vert, whiff_delta=float(sw),
                                             contact_delta=float(sx), confidence=3))
                    coach = CoachProfile(tuple(tags))
                lg, hit = m.predict_pair(Q, coach=coach)
                acc["no report" if rho is None else f"report rho={rho}"] = _sse(hit, y_w, bip, y_x)
                if rho:
                    tr = CoachProfile(coach.tags, trust=rho)
                    _, hit_t = m.predict_pair(Q, coach=tr)
                    acc[f"report rho={rho}, trust={rho}"] = _sse(hit_t, y_w, bip, y_x)
                if rho is None:
                    acc["base"] = _sse(lg, y_w, bip, y_x)
            per_h[b] = acc
        if per_h:
            _skill_table(per_h, "base", ["no report"] + [f"report rho={r}" for r in rhos]
                         + [f"report rho={r}, trust={r}" for r in rhos if r],
                         f" N = {n} swings of his own data ({len(per_h)} hitters); 'base' = league-only, no hitter data")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batters", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    ap.add_argument("--tests", default="6,7,8")
    a = ap.parse_args(argv)
    tests = set(a.tests.split(","))
    swings_by_hitter: dict[str, list[SwingRow]] = {}
    for t in _read(sorted(glob.glob(str(pathlib.Path(a.batters) / "*.csv")))):
        for s in parse_swings(t):
            swings_by_hitter.setdefault(s.batter, []).append(s)
    league_train = [s for rows in swings_by_hitter.values() for s in rows if s.date < a.cutoff]
    print(f"hitters: {len(swings_by_hitter)}, league training swings: {len(league_train)}, cutoff {a.cutoff}")
    if "6" in tests:
        test6(swings_by_hitter, a.cutoff, league_train)
    if "7" in tests:
        test7(swings_by_hitter, a.cutoff, league_train)
    if "8" in tests:
        test8(swings_by_hitter, a.cutoff, league_train)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
