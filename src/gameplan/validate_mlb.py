"""MLB validation of the parts that were still assumptions, on real outcomes.

  V1  Called-strike surface: fitted kernel vs the logistic stand-in, held out.
  V2  Calibration of the decision layer's two halves: predicted swing EV vs realized swing value, and
      predicted take EV vs realized take value, by decile, against starters, held out.
  V3  Situation weights against real run expectancy (delta_run_exp): does adding base-out and
      score / inning adjustments make the GO / NO_GO call separate swings from takes better in the
      spots where they change the call? Plus how often hitters already follow the call.
  V4  Year over year: hitter models fit on 2024, scored on 2025 (and combined with early 2025).

    python -m gameplan.validate_mlb --b25 data/b3 --b24 data/b24 --pitchers data/p2
"""
from __future__ import annotations

import argparse
import glob
import pathlib

import numpy as np

from .baseout import inning_bucket, score_bucket
from .decision import (
    DEFAULT, SituationConfig, SituationPolicy, apply_situation, deltas_np, evs_np, p_called_strike,
    realized_value, situation_weights,
)
from .savant import SwingRow, parse_swings
from .shape import ContactModel, filter_starts, parse_pitches
from .study import _boot, _fmt, _read
from .stats import benjamini_hochberg, holm, interval, report_family, two_sided_p, two_way_draws
from .success import record
from .zone import CalledStrikeModel

CUTOFF = "2025-07-01"


def load_batters(directory: str, takes: bool = True) -> dict[str, list[SwingRow]]:
    out: dict[str, list[SwingRow]] = {}
    for t in _read(sorted(glob.glob(str(pathlib.Path(directory) / "*.csv")))):
        for s in parse_swings(t, include_takes=takes):
            out.setdefault(s.batter, []).append(s)
    return out


def load_start_keys(directory: str) -> set:
    keys = set()
    for t in _read(sorted(glob.glob(str(pathlib.Path(directory) / "*.csv")))):
        keys |= {(p.game_pk, p.at_bat, p.pitch_no) for p in filter_starts(parse_pitches(t))}
    return keys


# ------------------------------------------------------------------ V1

def v1_zone(events_by_hitter, cutoff):
    print("\n== V1: called-strike surface, held-out taken pitches (called strike vs ball)")
    train = [s for r in events_by_hitter.values() for s in r if not s.swing and s.date < cutoff]
    test = [s for r in events_by_hitter.values() for s in r
            if not s.swing and s.date >= cutoff and s.take_call in ("strike", "ball") and s.x_away is not None]
    zm = CalledStrikeModel(train)
    x = np.array([s.x_away for s in test])
    z = np.array([s.z for s in test])
    sb = np.array([s.sz_bot or 1.5 for s in test])
    st = np.array([s.sz_top or 3.5 for s in test])
    y = np.array([s.take_call == "strike" for s in test], float)
    stand_in = np.array([p_called_strike(a, b, c, d) for a, b, c, d in zip(x, z, sb, st)])
    kern_pooled = zm.p(x, z, sb, st)
    kern = zm.p(x, z, sb, st, strikes=np.array([s.strikes for s in test]))
    edge = np.abs(stand_in - 0.5) < 0.45          # not obviously in or out
    strikes = np.array([s.strikes for s in test])
    print(f"  train takes {zm.n}, test takes {len(test)}, borderline {int(edge.sum())}")
    for name, p in (("logistic stand-in", stand_in), ("kernel, pooled", kern_pooled), ("kernel, by strike count", kern)):
        print(f"  {name:<18} Brier all {np.mean((p - y) ** 2):.4f}   borderline {np.mean(((p - y) ** 2)[edge]):.4f}   "
              f"mean pred {p[edge].mean():.3f} vs actual {y[edge].mean():.3f} (borderline)")
    print("  borderline strike rate, actual vs fitted, by strikes: "
          + "  ".join(f"{k}: {y[edge & (strikes == k)].mean():.3f} vs {kern[edge & (strikes == k)].mean():.3f}"
                      for k in (0, 1, 2)))
    return zm


# ------------------------------------------------------------------ shared per-hitter frames

def _frames(events_by_hitter, cutoff, start_keys, league_train, zm, min_train=300):
    """Per hitter: held-out pitches vs starters with hitter-model predictions for the pitch's own
    location and shape. Returns a list of dicts of aligned numpy arrays."""
    league = ContactModel([], league_train, mode="shape")
    out = []
    for b, rows in events_by_hitter.items():
        train = [s for s in rows if s.swing and s.date < cutoff]
        test = [s for s in rows if s.date >= cutoff and (s.game_pk, s.at_bat, s.pitch_no) in start_keys
                and s.x_away is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)]
        if len(train) < min_train or not test:
            continue
        m = ContactModel.for_hitter(train, league)
        Q = np.array([(s.x_away, s.z, s.velo, s.ivb, s.hb, s.vaa) for s in test], float)
        lg, hit = m.predict_pair(Q)
        sb = np.array([s.sz_bot or 1.5 for s in test])
        st = np.array([s.sz_top or 3.5 for s in test])
        f = {
            "hitter": b, "n": len(test),
            "swing": np.array([s.swing for s in test]),
            "whiff": np.array([s.whiff for s in test]),
            "xwoba": [s.xwoba for s in test], "take_call": [s.take_call for s in test],
            "balls": np.array([s.balls for s in test]), "strikes": np.array([s.strikes for s in test]),
            "outs": np.array([s.outs if s.outs is not None else -1 for s in test]),
            "bases": [s.bases for s in test],
            "lead": np.array([s.score_diff if s.score_diff is not None else 0 for s in test]),
            "inning": np.array([s.inning or 1 for s in test]),
            "rv": np.array([s.run_exp if s.run_exp is not None else np.nan for s in test]),
            "pitcher": np.array([s.pitcher for s in test]), "game": np.array([s.game_pk for s in test]), "p_lg": lg,
            "p": hit, "p_cs": zm.p(np.array([s.x_away for s in test]), np.array([s.z for s in test]), sb, st,
                                   strikes=np.array([s.strikes for s in test])),
        }
        f["value"] = np.array([
            realized_value(s.swing, s.whiff, s.xwoba, s.take_call, s.balls, s.strikes, DEFAULT) is None and np.nan
            or realized_value(s.swing, s.whiff, s.xwoba, s.take_call, s.balls, s.strikes, DEFAULT)
            for s in test], float)
        out.append(f)
    return out


# ------------------------------------------------------------------ V2

def v2_calibration(frames):
    print("\n== V2: is each half of the decision layer calibrated? (held out, vs starters, count-aware, no situation)")
    print("   Slope intervals: two-way cluster bootstrap over hitters AND pitchers.")
    pvals, max_gap = {}, 0.0
    for name, want_swing, key in (("swing EV (realized: whiff/foul/xwOBA value of the state reached)", True, "swing"),
                                  ("take EV (realized: value of the count after the call)", False, "take")):
        pred, real, hid, pit = [], [], [], []
        for k, f in enumerate(frames):
            sw, tk = evs_np(f["p"]["whiff"], f["p"]["foul"], f["p"]["xw"], f["p_cs"], f["balls"], f["strikes"])
            sel = (f["swing"] == want_swing) & ~np.isnan(f["value"])
            pred.append((sw if want_swing else tk)[sel])
            real.append(f["value"][sel])
            hid.append(np.full(sel.sum(), k))
            pit.append(f["pitcher"][sel])
        pred, real, hid, pit = np.concatenate(pred), np.concatenate(real), np.concatenate(hid), np.concatenate(pit)
        edges = np.percentile(pred, np.linspace(0, 100, 11))
        print(f"  {name}: {len(pred)} pitches")
        print("    decile  mean predicted  mean realized  (gap)")
        for d in range(10):
            m = (pred >= edges[d]) & (pred <= edges[d + 1] if d == 9 else pred < edges[d + 1])
            gap = real[m].mean() - pred[m].mean()
            max_gap = max(max_gap, abs(gap))
            print(f"    {d + 1:>5}  {pred[m].mean():>14.3f}  {real[m].mean():>13.3f}  ({gap:+.3f})")
        _, pidx = np.unique(pit, return_inverse=True)

        def wslope(w):
            pm, rm = (w * pred).sum() / w.sum(), (w * real).sum() / w.sum()
            return float((w * (pred - pm) * (real - rm)).sum() / (w * (pred - pm) ** 2).sum())
        point, draws = two_way_draws(hid, pidx, wslope, 300)
        print(f"    calibration slope (1.0 = perfect): {_fmt(interval(point, draws))}")
        print(f"    mean error (realized - predicted): {np.mean(real - pred):+.4f}")
        record(f"cal.{key}_slope", point)
        pvals[f"{key} EV calibration slope = 1"] = two_sided_p(draws, 1.0)
    record("cal.max_decile_gap", max_gap)
    return pvals


# ------------------------------------------------------------------ V3

SPOTS = {
    "runner on 3rd, < 2 outs": lambda f: np.array([b[2] for b in f["bases"]]) & (f["outs"] < 2) & (f["outs"] >= 0),
    "RISP, 2 outs": lambda f: np.array([b[1] or b[2] for b in f["bases"]]) & (f["outs"] == 2),
    "runner on 1st only, < 2 outs": lambda f: np.array([b[0] and not (b[1] or b[2]) for b in f["bases"]]) & (f["outs"] < 2) & (f["outs"] >= 0),
    "late and close (7th+, within 1)": lambda f: (f["inning"] >= 7) & (np.abs(f["lead"]) <= 1),
    "all pitches": lambda f: np.ones(f["n"], bool),
}
OFF = SituationPolicy.OFF
VARIANTS = {
    "count only": SituationConfig(OFF, OFF, OFF, OFF, OFF),
    "base-out MILD": SituationConfig(SituationPolicy.MILD, SituationPolicy.MILD, SituationPolicy.MILD, OFF, OFF),
    "base-out STRONG": SituationConfig(SituationPolicy.STRONG, SituationPolicy.STRONG, SituationPolicy.STRONG, OFF, OFF),
    "score/inning MILD": SituationConfig(OFF, OFF, OFF, OFF, SituationPolicy.MILD),
    "score/inning STRONG": SituationConfig(OFF, OFF, OFF, OFF, SituationPolicy.STRONG),
    "all MILD": SituationConfig(SituationPolicy.MILD, SituationPolicy.MILD, SituationPolicy.MILD, OFF, SituationPolicy.MILD),
}


def _situation_delta(f, config):
    """Swing-minus-take per pitch under a config (grouped by distinct situation for speed)."""
    d = np.zeros(f["n"])
    keys = {}
    for i in range(f["n"]):
        keys.setdefault((f["outs"][i], f["bases"][i], score_bucket(int(f["lead"][i])),
                         inning_bucket(int(f["inning"][i])), int(f["lead"][i]), int(f["inning"][i])), []).append(i)
    for (outs, bases, _, _, lead, inn), idx in keys.items():
        w = situation_weights(max(int(outs), 0), bases, lead, inn, config)
        cv = apply_situation(DEFAULT, w)
        ix = np.array(idx)
        d[ix] = deltas_np(f["p"]["whiff"][ix], f["p"]["foul"][ix], f["p"]["xw"][ix], f["p_cs"][ix],
                          f["balls"][ix], f["strikes"][ix], cv)
    return d


def v3_situation(frames, go=0.02):
    print("\n== V3: do situation weights improve the call against REAL run expectancy? (held out, vs starters)")
    print("   S_RV = [mean run value(swing) - mean run value(take)] in GO pitches minus the same in NO_GO pitches,")
    print("   in runs, restricted to each spot. Higher is better. Paired differences vs count only, CI by hitter.")
    acc = {sp: {v: [] for v in VARIANTS} for sp in SPOTS}
    chg = {sp: {v: [] for v in VARIANTS} for sp in SPOTS}    # pitches whose GO status the variant changed
    comp = {sp: [] for sp in SPOTS}
    for f in frames:
        deltas = {v: _situation_delta(f, c) for v, c in VARIANTS.items()}
        ok = ~np.isnan(f["rv"])
        for sp, pick in SPOTS.items():
            base = ok & pick(f)
            if not base.any():
                for v in VARIANTS:
                    acc[sp][v].append(np.zeros((2, 2, 2)))
                    chg[sp][v].append(np.zeros((2, 2, 2)))
                comp[sp].append(np.zeros(4))
                continue
            for v, d in deltas.items():
                rec = np.zeros((2, 2, 2))            # [class GO/NO_GO][swing/take][sum, n]
                for ci, cls in enumerate((d >= go, d <= -go)):
                    for si, sw in enumerate((True, False)):
                        m = base & cls & (f["swing"] == sw)
                        rec[ci, si] = (f["rv"][m].sum(), m.sum())
                acc[sp][v].append(rec)
                d0_ = deltas["count only"]
                ch = np.zeros((2, 2, 2))             # [promoted into GO / demoted out of GO][swing/take][sum, n]
                for ci, cls in enumerate(((d0_ < go) & (d >= go), (d0_ >= go) & (d < go))):
                    for si, sw in enumerate((True, False)):
                        m = base & cls & (f["swing"] == sw)
                        ch[ci, si] = (f["rv"][m].sum(), m.sum())
                chg[sp][v].append(ch)
            d0 = deltas["count only"]
            comp[sp].append(np.array([(base & (d0 >= go) & f["swing"]).sum(), (base & (d0 >= go)).sum(),
                                      (base & (d0 <= -go) & ~f["swing"]).sum(), (base & (d0 <= -go)).sum()], float))

    def s_rv(recs):
        a = np.sum(recs, axis=0)
        g = lambda c: a[c, 0, 0] / max(a[c, 0, 1], 1) - a[c, 1, 0] / max(a[c, 1, 1], 1)
        return g(0) - g(1)
    for sp in SPOTS:
        c = np.sum(comp[sp], axis=0)
        n_pitch = int(sum(r[0, 0, 1] + r[0, 1, 1] + r[1, 0, 1] + r[1, 1, 1] for r in acc[sp]["count only"]))
        print(f"  [{sp}]  classified pitches {n_pitch}; hitters already swing at {c[0] / max(c[1], 1):.0%} of "
              f"GO pitches and take {c[2] / max(c[3], 1):.0%} of NO_GO pitches")
        a0 = np.sum(acc[sp]["count only"], axis=0)
        g = lambda c: a0[c, 0, 0] / max(a0[c, 0, 1], 1) - a0[c, 1, 0] / max(a0[c, 1, 1], 1)
        print(f"    swing minus take run value: GO pitches {g(0):+.3f} runs, NO_GO pitches {g(1):+.3f} runs per pitch")
        idx = {k: i for i, k in enumerate(range(len(frames)))}
        base = {i: acc[sp]["count only"][i] for i in idx}
        print(f"    count only                S_RV {_fmt(_boot(base, s_rv, 200))}")
        for v in list(VARIANTS)[1:]:
            pair = {i: (acc[sp]["count only"][i], acc[sp][v][i]) for i in idx}
            stat = lambda vals: s_rv([x[1] for x in vals]) - s_rv([x[0] for x in vals])
            print(f"    {v:<25} paired diff vs count only {_fmt(_boot(pair, stat, 200))}")
        print("    pitches whose GO call the variant changed: swing-minus-take run value, promoted-to-GO minus demoted-from-GO")
        print("    (positive = the variant moved the right pitches; n = promoted swings+takes / demoted swings+takes)")
        for v in list(VARIANTS)[1:]:
            per = {i: chg[sp][v][i] for i in idx}

            def gapdiff(recs):
                a = np.sum(recs, axis=0)
                g = lambda c: a[c, 0, 0] / max(a[c, 0, 1], 1) - a[c, 1, 0] / max(a[c, 1, 1], 1)
                return g(0) - g(1)
            tot = np.sum(list(per.values()), axis=0)
            print(f"    {v:<25} {_fmt(_boot(per, gapdiff, 200))}   n = {int(tot[0, :, 1].sum())} / {int(tot[1, :, 1].sum())}")


# ------------------------------------------------------------------ V5

def v5_separation(frames, go=0.02, n_boot=300):
    """Separation against real run value (delta_run_exp, independent of every table in the model), with the
    two-way bootstrap. Tests: (a) hitter model vs league model where they disagree, (b) removing count
    awareness."""
    print("\n== V5: separation against real run value; two-way cluster bootstrap (hitters and pitchers)")
    cat = lambda k: np.concatenate([f[k] for f in frames])
    hid = np.concatenate([np.full(f["n"], k) for k, f in enumerate(frames)])
    _, pidx = np.unique(cat("pitcher"), return_inverse=True)
    swing, rv = cat("swing"), cat("rv")
    ok = ~np.isnan(rv)

    def deltas(pkey, blind):
        out = []
        for f in frames:
            b = np.zeros(f["n"], int) if blind else f["balls"]
            s_ = np.zeros(f["n"], int) if blind else f["strikes"]
            out.append(deltas_np(f[pkey]["whiff"], f[pkey]["foul"], f[pkey]["xw"], f["p_cs"], b, s_))
        return np.concatenate(out)
    dA, dB, dC = deltas("p", False), deltas("p_lg", False), deltas("p", True)

    def gap(mask, w):
        a, b = mask & swing & ok, mask & ~swing & ok
        wa, wb = (w * a).sum(), (w * b).sum()
        if wa == 0 or wb == 0:
            return 0.0
        return float((w * a * np.nan_to_num(rv)).sum() / wa - (w * b * np.nan_to_num(rv)).sum() / wb)

    def S(d, w):
        return gap(d >= go, w) - gap(d <= -go, w)
    dis_go, dis_no = (dA >= go) & ~(dB >= go), (dA <= -go) & ~(dB <= -go)
    stats = {
        "S, hitter model, count aware (runs)": lambda w: S(dA, w),
        "S lost when count awareness is removed (runs; negative = count helps)": lambda w: S(dC, w) - S(dA, w),
        "disagreement: swing-take gap in hitter-GO minus hitter-NO_GO (runs)": lambda w: gap(dis_go, w) - gap(dis_no, w),
    }
    pv = {}
    for name, fn in stats.items():
        point, draws = two_way_draws(hid, pidx, fn, n_boot)
        pt, lo, hi = interval(point, draws)
        print(f"  {name:<72} {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]")
        if name.startswith("S lost"):
            record("sep.count_removal_hurts", hi)
            pv["removing count awareness changes S"] = two_sided_p(draws, 0.0)
        elif name.startswith("disagreement"):
            record("sep.disagree_ci_low", lo)
            pv["hitter-vs-league disagreement gap > 0"] = two_sided_p(draws, 0.0)
    print(f"  pitches in hitter-GO-only / hitter-NO_GO-only sets: {int(dis_go.sum())} / {int(dis_no.sum())}")
    return pv


# ------------------------------------------------------------------ V4

def v4_year_over_year(b24, b25, cutoff):
    print("\n== V4: year over year. Fit on 2024, score 2025 after the cutoff (all pitchers, swings)")
    s24 = {b: [s for s in r if s.swing] for b, r in b24.items()}
    s25 = {b: [s for s in r if s.swing] for b, r in b25.items()}
    league = ([s for r in s24.values() for s in r] + [s for r in s25.values() for s in r if s.date < cutoff])
    lm = {m: ContactModel([], league, mode=m) for m in ("type", "shape")}
    variants = ["A type, league only (baseline)", "B shape, league only", "C shape, hitter: 2024 only",
                "D shape, hitter: 2025 before cutoff only", "E shape, hitter: 2024 + 2025 before cutoff"]
    per_h = {}
    for b, rows in s25.items():
        h24 = s24.get(b, [])
        h25 = [s for s in rows if s.date < cutoff]
        test = [s for s in rows if s.date >= cutoff]
        if len(h24) < 300 or len(h25) < 100 or len(test) < 150:
            continue
        Qm = lm["shape"]
        Q, mask = Qm.query_swings(test)
        test = [s for s, k in zip(test, mask) if k]
        y_w = np.array([s.whiff for s in test], float)
        bip = np.array([s.xwoba is not None for s in test], bool)
        y_x = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in test], float)
        su_m = np.array([s.squared_up is not None for s in test], bool)
        y_s = np.array([float(s.squared_up) if s.squared_up is not None else 0.0 for s in test], float)

        def err(p):
            return (float(((p["whiff"] - y_w) ** 2).sum()), float(len(y_w)),
                    float(((p["xw"] - y_x)[bip] ** 2).sum()), float(bip.sum()),
                    float(((p["su"] - y_s)[su_m] ** 2).sum()), float(su_m.sum()))
        acc = {}
        Qt, _ = lm["type"].query_swings(test)
        acc[variants[0]] = err(lm["type"].predict(Qt, use_hitter=False))
        acc[variants[1]] = err(lm["shape"].predict(Q[mask.nonzero()[0] * 0 + np.arange(len(Q))] if False else lm["shape"].query_swings(test)[0], use_hitter=False))
        for name, data in ((variants[2], h24), (variants[3], h25), (variants[4], h24 + h25)):
            m = ContactModel.for_hitter(data, lm["shape"])
            acc[name] = err(m.predict(m.query_swings(test)[0], use_hitter=True))
        per_h[b] = acc
    print(f"  hitters with 2024 and 2025 data: {len(per_h)}")
    for ti, tname in enumerate(["whiff Brier", "xwOBAcon MSE", "squared-up Brier"]):
        print(f"  {tname}: skill vs {variants[0]}")
        for v in variants[1:]:
            def stat(vals, v=v, ti=ti):
                return 1.0 - sum(x[v][2 * ti] for x in vals) / sum(x[variants[0]][2 * ti] for x in vals)
            res = _boot(per_h, stat, 300)
            print(f"    {v:<44} {_fmt(res)}")
            if v == variants[2] and ti in (0, 1):
                record("skill.whiff_yoy_ci_low" if ti == 0 else "skill.xw_yoy_ci_low", res[1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--b24", default=None)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--tests", default="1,2,3,4,5")
    ap.add_argument("--cutoff", default=CUTOFF)
    a = ap.parse_args(argv)
    tests = set(a.tests.split(","))
    b25 = load_batters(a.b25)
    print(f"2025 hitters: {len(b25)}")
    zm = v1_zone(b25, a.cutoff) if tests & {"1", "2", "3", "5"} else None
    if tests & {"2", "3", "5"}:
        start_keys = load_start_keys(a.pitchers)
        league_train = [s for r in b25.values() for s in r if s.swing and s.date < a.cutoff]
        frames = _frames(b25, a.cutoff, start_keys, league_train, zm)
        print(f"hitters framed: {len(frames)}, pitches: {sum(f['n'] for f in frames)}")
        family = {}
        if "2" in tests:
            family.update(v2_calibration(frames))
        if "3" in tests:
            v3_situation(frames)
        if "5" in tests:
            family.update(v5_separation(frames))
        if family:
            print("\n== Headline tests, multiplicity-adjusted (Holm controls any false positive; BH controls false discovery)")
            print(report_family(family))
    if "4" in tests and a.b24:
        v4_year_over_year(load_batters(a.b24, takes=False), {b: [s for s in r if s.swing] for b, r in b25.items()}, a.cutoff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
