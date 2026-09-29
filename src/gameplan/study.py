"""Out-of-sample viability study for the shape-aware, arsenal- and TTO-aware, count-aware engine.

    python -m gameplan.study --batters data/b --pitchers data/p [--cutoff 2025-07-01]

Everything is fit on data before the cutoff date and scored on data on or after it.

Test 0  Is hitter ability (whiff, xwOBAcon, squared-up, CQ) stable enough to plan around?
        Train-vs-test correlation across hitters.
Test 1  Do hitter-specific and pitch-shape-aware models predict held-out swings better than a
        league, location + pitch-type model? Brier / MSE skill with a hitter-cluster bootstrap.
Test 2  Is the shape model calibrated by time through the order for starters? If residuals are flat
        across TTO, the shape and location already carry the TTO effect.
Test 3  Does the count-aware GO / NO_GO call separate pitches where swinging beat taking from pitches
        where taking beat swinging, against starters, and which ingredients earn their place
        (hitter data, pitch shape, TTO-specific arsenal, count awareness)?
Test 4  Descriptive: how starters change by time through the order.
"""
from __future__ import annotations

import argparse
import glob
import pathlib
import statistics
from collections import defaultdict

import numpy as np

from .decision import CountValues, DEFAULT, deltas_np, fit_count_values, p_called_strike, realized_value
from .savant import SwingRow, contact_quality, parse_swings
from . import fatigue
from .shape import (
    FASTBALLS, ContactModel, PitchRow, build_arsenal, cap_tto, fit_tto_shifts, parse_pitches, raw_query,
)

RNG = np.random.default_rng(7)


def _read(paths):
    for p in paths:
        with open(p, encoding="utf-8-sig") as fh:
            yield fh.read()


def _boot(per_hitter: dict, stat, n=400):
    """Cluster bootstrap over hitters. per_hitter: {hitter: any}; stat(list_of_values) -> float."""
    keys = list(per_hitter)
    vals = [per_hitter[k] for k in keys]
    point = stat(vals)
    draws = []
    for _ in range(n):
        idx = RNG.integers(0, len(vals), len(vals))
        draws.append(stat([vals[i] for i in idx]))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return point, lo, hi


def _fmt(t):
    return f"{t[0]:+.4f} [{t[1]:+.4f}, {t[2]:+.4f}]"


# ------------------------------------------------------------------ tests

def test0(train_by, test_by):
    print("\n== Test 0: is hitter ability stable? (train vs held-out, across hitters)")
    rows = []
    for b in train_by:
        tr, te = train_by[b], test_by.get(b, [])
        if len(tr) < 200 or len(te) < 100:
            continue
        def m(ss):
            n = len(ss)
            bip = [s for s in ss if s.xwoba is not None]
            su = [s.squared_up for s in ss if s.squared_up is not None]
            return (sum(s.whiff for s in ss) / n,
                    sum(s.xwoba for s in bip) / len(bip) if bip else np.nan,
                    sum(su) / len(su) if su else np.nan, contact_quality(ss) or np.nan)
        rows.append(m(tr) + m(te))
    A = np.array(rows, float)
    for k, name in enumerate(["whiff rate", "xwOBAcon", "squared-up rate on BIP", "CQ"]):
        ok = ~np.isnan(A[:, k]) & ~np.isnan(A[:, k + 4])
        r = np.corrcoef(A[ok, k], A[ok, k + 4])[0, 1]
        print(f"  {name:<24} r = {r:+.2f}  (n={ok.sum()} hitters)")


def _predict_all(models, hitter_swings_test):
    """Test 1 predictions for one hitter's held-out swings. Returns dict of arrays keyed by variant."""
    out = {}
    for mode in ("type", "shape"):
        m = models[mode]
        Q, mask = m.query_swings(hitter_swings_test)
        if not len(Q):
            continue
        lg, hit = m.predict_pair(Q)
        out[(mode, "league")] = (lg, mask)
        out[(mode, "hitter")] = (hit, mask)
    return out


def test1_and_2(swings_by_hitter, cutoff, league_train, starters):
    print("\n== Test 1: held-out swing prediction skill vs league / location+type model")
    variants = [("type", "league"), ("type", "hitter"), ("shape", "league"), ("shape", "hitter")]
    names = {v: f"{v[0]}-{v[1]}" for v in variants}
    # league models once
    league_models = {mode: ContactModel([], league_train, mode=mode) for mode in ("type", "shape")}
    per_h = {}
    tto_rows = []
    for b, rows in swings_by_hitter.items():
        train = [s for s in rows if s.date < cutoff]
        test = [s for s in rows if s.date >= cutoff]
        if len(train) < 300 or len(test) < 150:
            continue
        models = {}
        for mode in ("type", "shape"):
            m = ContactModel(train, [], mode=mode)
            m._l = league_models[mode]._l
            m._g = league_models[mode]._g
            models[mode] = m
        # keep only swings with all shape features so every variant scores the same rows
        Qs, mask = models["shape"].query_swings(test)
        test = [s for s, k in zip(test, mask) if k]
        preds = _predict_all(models, test)
        if ("shape", "hitter") not in preds:
            continue
        y_w = np.array([s.whiff for s in test], float)
        bip = np.array([s.xwoba is not None for s in test], bool)
        y_x = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in test], float)
        su_m = np.array([s.squared_up is not None for s in test], bool)
        y_s = np.array([float(s.squared_up) if s.squared_up is not None else 0.0 for s in test], float)
        acc = {}
        for v in variants:
            p, _ = preds[v]
            acc[v] = (
                float(((p["whiff"] - y_w) ** 2).sum()), float(len(y_w)),
                float(((p["xw"] - y_x)[bip] ** 2).sum()), float(bip.sum()),
                float(((p["su"] - y_s)[su_m] ** 2).sum()), float(su_m.sum()),
            )
        per_h[b] = acc
        # keep hitter-shape predictions for TTO calibration vs starters
        p, _ = preds[("shape", "hitter")]
        for k, s in enumerate(test):
            if s.pitcher in starters and s.tto:
                tto_rows.append((cap_tto(s.tto), float(s.whiff), float(p["whiff"][k]),
                                 s.xwoba, float(p["xw"][k])))
    base = ("type", "league")
    for ti, tname in enumerate(["whiff Brier", "xwOBAcon MSE", "squared-up Brier"]):
        print(f"  {tname}: skill vs {names[base]} (1 - err/err_base, higher is better; 95% CI by hitter)")
        for v in variants[1:]:
            def stat(vals, v=v, ti=ti):
                e = sum(x[v][2 * ti] for x in vals)
                e0 = sum(x[base][2 * ti] for x in vals)
                return 1.0 - e / e0
            print(f"    {names[v]:<14} {_fmt(_boot(per_h, stat))}")
    print(f"  hitters scored: {len(per_h)}")

    print("\n== Test 2: shape-hitter model calibration by time through the order (vs starters, held out)")
    print("  TTO   n_swings  whiff actual  whiff pred  | n_bip  xwOBAcon actual  pred")
    for t in (1, 2, 3):
        r = [x for x in tto_rows if x[0] == t]
        if not r:
            continue
        rb = [x for x in r if x[3] is not None]
        print(f"  {t}{'+' if t == 3 else ' '}  {len(r):>9}  {np.mean([x[1] for x in r]):>12.3f}  "
              f"{np.mean([x[2] for x in r]):>10.3f}  | {len(rb):>5}  {np.mean([x[3] for x in rb]):>15.3f}  "
              f"{np.mean([x[4] for x in rb]):.3f}")
    return per_h


def test3(events_by_hitter, cutoff, league_train, pitch_by_pitcher, cv: CountValues):
    print("\n== Test 3: does the call separate swing-beats-take from take-beats-swing? (vs starters)")
    print("   S = [mean value(swing) - mean value(take)] in GO pitches minus the same in NO_GO pitches")
    print("   (wOBA scale, higher is better; selection bias applies, compare variants not levels)")
    arsenals = {}
    for pid, rows in pitch_by_pitcher.items():
        arsenals[pid] = {"all": build_arsenal(rows, cutoff)}
        for t in (1, 2, 3):
            arsenals[pid][t] = build_arsenal(rows, cutoff, tto=t)
    league_models = {mode: ContactModel([], league_train, mode=mode) for mode in ("type", "shape")}
    vs_starters = [s for rows in events_by_hitter.values() for s in rows
                   if s.swing and s.date < cutoff and s.pitcher in arsenals]
    shifts = fit_tto_shifts(league_models["shape"], vs_starters)
    print("  TTO shifts from training swings vs starters (whiff, xwOBAcon): "
          + "  ".join(f"TTO{t}: ({w:+.3f}, {x:+.3f})" for t, (w, x) in shifts.items()))
    variants = {
        "V1 league, type, count": ("type", False, "all", True, False),
        "V2 hitter, type, count": ("type", True, "all", True, False),
        "V3 hitter, shape, all-TTO arsenal": ("shape", True, "all", True, False),
        "V4 hitter, shape, TTO arsenal": ("shape", True, "tto", True, False),
        "V5 hitter, shape, TTO, count-blind": ("shape", True, "tto", False, False),
        "V6 league, shape, TTO arsenal": ("shape", False, "tto", True, False),
        "V7 hitter, shape, TTO arsenal + TTO shift": ("shape", True, "tto", True, True),
        "V8 league, shape, TTO arsenal + TTO shift": ("shape", False, "tto", True, True),
    }
    dis_acc: dict = {}
    acc: dict = {}
    n_pitches = 0
    for b, rows in events_by_hitter.items():
        train = [s for s in rows if s.swing and s.date < cutoff]
        test = [s for s in rows if s.date >= cutoff and s.pitcher in arsenals and s.tto]
        if len(train) < 300 or not test:
            continue
        models = {}
        for mode in ("type", "shape"):
            m = ContactModel(train, [], mode=mode)
            m._l, m._g = league_models[mode]._l, league_models[mode]._g
            models[mode] = m
        # build query rows: the pitch's own location, arsenal shape for its type
        keep, q_type, q_shape_all, q_shape_tto = [], [], [], []
        for s in test:
            ars = arsenals[s.pitcher]
            a_all, a_t = ars["all"].get(s.pitch_type), ars[cap_tto(s.tto)].get(s.pitch_type)
            if s.x_away is None or a_all is None or a_t is None:
                continue
            keep.append(s)
            q_type.append(raw_query("type", s.x_away, s.z, s.pitch_type, 0, 0, 0, 0))
            q_shape_all.append(raw_query("shape", s.x_away, s.z, s.pitch_type, a_all.velo, a_all.ivb, a_all.hb, a_all.vaa))
            q_shape_tto.append(raw_query("shape", s.x_away, s.z, s.pitch_type, a_t.velo, a_t.ivb, a_t.hb, a_t.vaa))
        if not keep:
            continue
        n_pitches += len(keep)
        bal = np.array([s.balls for s in keep])
        stk = np.array([s.strikes for s in keep])
        p_cs = np.array([p_called_strike(s.x_away, s.z, s.sz_bot or 1.5, s.sz_top or 3.5) for s in keep])
        val = [realized_value(s.swing, s.whiff, s.xwoba, s.take_call, s.balls, s.strikes, cv) for s in keep]
        ok = np.array([v is not None for v in val])
        v = np.array([x if x is not None else 0.0 for x in val])
        is_swing = np.array([s.swing for s in keep])
        Qmap = {("type", "all"): np.array(q_type, float), ("shape", "all"): np.array(q_shape_all, float),
                ("shape", "tto"): np.array(q_shape_tto, float)}
        cache = {}
        t_arr = np.array([cap_tto(s.tto) for s in keep])
        dw = np.array([shifts[t][0] for t in t_arr])
        dx = np.array([shifts[t][1] for t in t_arr])
        cls_by = {}
        for name, (mode, use_h, arsn, count_aware, shift) in variants.items():
            Q = Qmap[(mode, "all" if mode == "type" else arsn)]
            key = (mode, arsn if mode == "shape" else "all")
            if key not in cache:
                cache[key] = models[mode].predict_pair(Q)
            lg, hit = cache[key]
            p = hit if use_h else lg
            wh, xw = p["whiff"], p["xw"]
            if shift:
                wh, xw = np.clip(wh + dw, 0.0, 0.95), xw + dx
            d = deltas_np(wh, p["foul"], xw, p_cs, bal if count_aware else 0 * bal,
                          stk if count_aware else 0 * stk, cv)
            cls = np.where(d >= 0.02, 1, np.where(d <= -0.02, -1, 0))
            cls_by[name] = cls
            rec = {}
            for c, cname in ((1, "GO"), (-1, "NO_GO")):
                for sw, sname in ((True, "swing"), (False, "take")):
                    m = ok & (cls == c) & (is_swing == sw)
                    rec[(cname, sname)] = (float(v[m].sum()), float(m.sum()))
            acc.setdefault(name, {})[b] = rec
        # pitches where the hitter model and the league model disagree (same shape, TTO, shift)
        for hname, lname in (("V7 hitter, shape, TTO arsenal + TTO shift", "V8 league, shape, TTO arsenal + TTO shift"),
                             ("V2 hitter, type, count", "V1 league, type, count")):
            ch, cl = cls_by[hname], cls_by[lname]
            rec = {}
            for c, cname in ((1, "GO"), (-1, "NO_GO")):
                for sw, sname in ((True, "swing"), (False, "take")):
                    m = ok & (ch == c) & (cl != c) & (is_swing == sw)
                    rec[(cname, sname)] = (float(v[m].sum()), float(m.sum()))
            dis_acc.setdefault(hname, {})[b] = rec
    print(f"  pitches scored: {n_pitches}, hitters: {len(events_by_hitter)}")

    def S(vals):
        def gap(c):
            sw = sum(x[(c, "swing")][0] for x in vals) / max(sum(x[(c, "swing")][1] for x in vals), 1)
            tk = sum(x[(c, "take")][0] for x in vals) / max(sum(x[(c, "take")][1] for x in vals), 1)
            return sw - tk
        return gap("GO") - gap("NO_GO")

    base = "V1 league, type, count"
    for name in variants:
        ph = acc.get(name, {})
        if not ph:
            continue
        cnt = {k: sum(x[k][1] for x in ph.values()) for k in [("GO", "swing"), ("GO", "take"),
                                                             ("NO_GO", "swing"), ("NO_GO", "take")]}
        print(f"  {name:<36} S {_fmt(_boot(ph, S))}   n(GO sw/tk, NO_GO sw/tk) = "
              f"{int(cnt[('GO','swing')])}/{int(cnt[('GO','take')])}, "
              f"{int(cnt[('NO_GO','swing')])}/{int(cnt[('NO_GO','take')])}")
    print("  Only pitches where the hitter model disagrees with the league model (hitter says GO / NO_GO,")
    print("  league says otherwise). If hitter data helps, swing-take gap should be higher in hitter-GO than in hitter-NO_GO:")
    for hname, ph in dis_acc.items():
        def gap(vals, c):
            sw = sum(x[(c, "swing")][0] for x in vals) / max(sum(x[(c, "swing")][1] for x in vals), 1)
            tk = sum(x[(c, "take")][0] for x in vals) / max(sum(x[(c, "take")][1] for x in vals), 1)
            return sw - tk
        n = {c: (int(sum(x[(c, 'swing')][1] for x in ph.values())), int(sum(x[(c, 'take')][1] for x in ph.values())))
             for c in ("GO", "NO_GO")}
        print(f"    {hname:<44} gap(hitter-GO) - gap(hitter-NO_GO) = {_fmt(_boot(ph, lambda v: gap(v, 'GO') - gap(v, 'NO_GO')))}"
              f"  n GO sw/tk {n['GO']}, NO_GO sw/tk {n['NO_GO']}")
    print("  paired difference in S vs V1 (same hitters, bootstrap):")
    b_ph = acc[base]
    for name in variants:
        if name == base or name not in acc:
            continue
        keys = [k for k in b_ph if k in acc[name]]
        pair = {k: (b_ph[k], acc[name][k]) for k in keys}
        stat = lambda vals: S([x[1] for x in vals]) - S([x[0] for x in vals])
        print(f"    {name:<36} {_fmt(_boot(pair, stat))}")


def test4(pitch_by_pitcher, cutoff):
    print("\n== Test 4: starters by time through the order (all starters pulled, full season)")
    print("  TTO  pitches  FB velo  FB usage  mean IVB(FB)")
    by = defaultdict(list)
    for rows in pitch_by_pitcher.values():
        for p in rows:
            if p.tto:
                by[cap_tto(p.tto)].append(p)
    for t in (1, 2, 3):
        r = by.get(t, [])
        fb = [p for p in r if p.pitch_type in FASTBALLS and p.velo]
        if r and fb:
            print(f"  {t}{'+' if t == 3 else ' '} {len(r):>8}  {np.mean([p.velo for p in fb]):>7.2f}  "
                  f"{len(fb) / len(r):>8.3f}  {np.mean([p.ivb for p in fb if p.ivb is not None]):>9.2f}")
    from .coach import FAMILY_OF
    print("  pitch mix by strike count and batter side (share of pitches: fastball / breaking / offspeed)")
    for label, pick in (("0 strikes", lambda p: p.strikes == 0), ("1 strike", lambda p: p.strikes == 1),
                        ("2 strikes", lambda p: p.strikes == 2), ("vs RHB", lambda p: p.stand == "R"),
                        ("vs LHB", lambda p: p.stand == "L")):
        rs = [p for rows in pitch_by_pitcher.values() for p in rows if pick(p)]
        if rs:
            f = [FAMILY_OF.get(p.pitch_type, "") for p in rs]
            print(f"    {label:<10} n={len(rs):>6}  " + "  ".join(f"{k} {f.count(k) / len(rs):.3f}" for k in ("FB", "BRK", "OFF")))
    # within-pitcher change in FB velo from TTO1 to TTO3
    diffs = []
    for rows in pitch_by_pitcher.values():
        a = [p.velo for p in rows if p.tto == 1 and p.pitch_type in FASTBALLS and p.velo]
        c = [p.velo for p in rows if p.tto and p.tto >= 3 and p.pitch_type in FASTBALLS and p.velo]
        if len(a) >= 100 and len(c) >= 50:
            diffs.append(np.mean(c) - np.mean(a))
    if diffs:
        print(f"  within-starter FB velo, TTO3+ minus TTO1: mean {np.mean(diffs):+.2f} mph over {len(diffs)} starters")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batters", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    ap.add_argument("--tests", default="0,1,3,4,5")
    a = ap.parse_args(argv)
    tests = set(a.tests.split(","))

    bpaths = sorted(glob.glob(str(pathlib.Path(a.batters) / "*.csv")))
    ppaths = sorted(glob.glob(str(pathlib.Path(a.pitchers) / "*.csv")))
    print(f"batters: {len(bpaths)} files, pitchers: {len(ppaths)} files, cutoff {a.cutoff}")
    events_by_hitter: dict[str, list[SwingRow]] = {}
    texts = []
    for t in _read(bpaths):
        texts.append(t)
        for s in parse_swings(t, include_takes=True):
            events_by_hitter.setdefault(s.batter, []).append(s)
    cv = fit_count_values(texts)
    del texts
    swings_by_hitter = {b: [s for s in rows if s.swing] for b, rows in events_by_hitter.items()}
    print("count values (expected final wOBA), fit on batters:")
    print("  " + "  ".join(f"{b}-{s}:{cv.table[(b, s)]:.3f}" for s in range(3) for b in range(4)))
    league_train = [s for rows in swings_by_hitter.values() for s in rows if s.date < a.cutoff]
    print(f"league training swings: {len(league_train)}")

    pitch_by_pitcher: dict[str, list[PitchRow]] = {}
    starters = set()
    for t in _read(ppaths):
        rows = parse_pitches(t)
        if rows:
            pitch_by_pitcher[rows[0].pitcher] = rows
            starters.add(rows[0].pitcher)

    if "0" in tests:
        test0({b: [s for s in r if s.date < a.cutoff] for b, r in swings_by_hitter.items()},
              {b: [s for s in r if s.date >= a.cutoff] for b, r in swings_by_hitter.items()})
    if "1" in tests:
        test1_and_2(swings_by_hitter, a.cutoff, league_train, starters)
    if "3" in tests:
        test3(events_by_hitter, a.cutoff, league_train, pitch_by_pitcher, cv)
    if "4" in tests:
        test4(pitch_by_pitcher, a.cutoff)
    if "5" in tests:
        print(fatigue.run(pitch_by_pitcher, events_by_hitter))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
