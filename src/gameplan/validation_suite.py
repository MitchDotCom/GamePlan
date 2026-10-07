"""Validation plan V5, V6, V7 and V9 (docs/VALIDATION_PLAN.md, amendment 2) for one season.

Stages, each skipped when its result file already exists (so a restart costs one stage):
  v6  two-way (hitter and starter) bootstrap on the V1 raw-outcome tally, K = 40
  v5  shrinkage sweep, K in {10, 20, 40, 80, 160}
  v7  Single-A style history caps: hitter history {100, 150, 200, 300}, starter starts {1, 2, 3}
  v9  hitter-specific referee (out-of-fold whiff and contact-quality shifts), full rerun of the V1 tally

Raw outcome = Statcast delta_run_exp, hitter side, net of the earlier-games league mean for the same kind of pitch.
Cost lift = how many more runs per 100 pitches the flagged pitches cost him than his other pitches.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import time
from collections import defaultdict

import numpy as np

from . import recognition_paths as rp

DEFS = rp.DEFS
NDRAW = 1000
CHUNK = 100
BASE_PATHS = ("L", "P", "E", "W", "U", "B1", "B3")
BASELINES = ("B1", "B3", "U")

_OUT: list[str] = []


def say(msg: str = "") -> None:
    print(msg, flush=True)
    _OUT.append(msg)


# ------------------------------------------------------------------ referee pieces

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def predictions(league, zone, P, t0):
    """League-model predictions for every pitch, kept so the referee can be recomputed with hitter-specific shifts."""
    out = defaultdict(list)
    for i in range(0, len(P), 40000):
        rows = P[i:i + 40000]
        Q, mask = league.query_swings(rows)
        assert mask.all()
        p = league.predict(Q, use_hitter=False)
        sb = np.array([s.sz_bot or 1.5 for s in rows])
        st = np.array([s.sz_top or 3.5 for s in rows])
        bal = np.array([s.balls for s in rows])
        stk = np.array([s.strikes for s in rows])
        for k in ("whiff", "foul", "xw"):
            out[k].append(p[k])
        out["pcs"].append(zone.p(Q[:, 0], Q[:, 1], sb, st, strikes=stk, balls=bal))
        say(f"  predictions {min(i + 40000, len(P))}/{len(P)} ({time.time() - t0:.0f}s)")
    pred = {k: np.concatenate(v) for k, v in out.items()}
    pred["bal"] = np.array([s.balls for s in P])
    pred["stk"] = np.array([s.strikes for s in P])
    pred["swung"] = np.array([s.swing for s in P])
    return pred


def losses(pred, w=None, x=None):
    wh, xw = pred["whiff"], pred["xw"]
    if w is not None:
        wh = _sigmoid(np.log(np.clip(wh, 1e-6, 1 - 1e-6) / (1 - np.clip(wh, 1e-6, 1 - 1e-6))) + w)
        xw = np.clip(xw + x, 0.0, 2.0)
    sw, tk = rp.evs_np(wh, pred["foul"], xw, pred["pcs"], pred["bal"], pred["stk"])
    loss = np.maximum(np.maximum(sw, tk) - np.where(pred["swung"], sw, tk), 0.0) / rp.SCALE
    return loss, (sw - tk) / rp.SCALE


def hitter_shifts(P, pred, k_whiff=200.0, k_xw=60.0):
    """Out-of-fold per-pitch shifts: a hitter's games alternate between two folds, and the shifts applied to one fold are estimated on the other."""
    bat = np.array([s.batter for s in P])
    hid = {b: i for i, b in enumerate(sorted(set(bat)))}
    h = np.array([hid[b] for b in bat])
    order = sorted(range(len(P)), key=lambda i: (P[i].date, P[i].game_pk))
    seen = defaultdict(dict)
    fold = np.zeros(len(P), int)
    for i in order:
        g = seen[bat[i]]
        gk = P[i].game_pk
        if gk not in g:
            g[gk] = len(g)
        fold[i] = g[gk] % 2
    swung = pred["swung"]
    y = np.array([float(s.whiff) for s in P])
    xo = np.array([np.nan if s.xwoba is None else s.xwoba for s in P])
    key = h * 2 + fold
    nk = 2 * len(hid)
    rw, vw, rx, nx = (np.zeros(nk) for _ in range(4))
    m = swung
    np.add.at(rw, key[m], (y - pred["whiff"])[m])
    np.add.at(vw, key[m], (pred["whiff"] * (1 - pred["whiff"]))[m])
    mb = swung & ~np.isnan(xo)
    np.add.at(rx, key[mb], (xo - pred["xw"])[mb])
    np.add.at(nx, key[mb], 1.0)
    other = h * 2 + (1 - fold)
    return rw[other] / (vw[other] + k_whiff), rx[other] / (nx[other] + k_xw)


def reliability_vals(P, loss, cells, ncell, minp):
    bat = np.array([s.batter for s in P])
    order = sorted(range(len(P)), key=lambda i: (P[i].date, P[i].game_pk))
    seen = defaultdict(dict)
    par = np.zeros(len(P), int)
    for i in order:
        g = seen[bat[i]]
        gk = P[i].game_pk
        if gk not in g:
            g[gk] = len(g)
        par[i] = g[gk] % 2
    tot = defaultdict(int)
    for b in bat:
        tot[b] += 1
    res = {}
    for d in DEFS:
        n = defaultdict(lambda: np.zeros(2))
        s = defaultdict(lambda: np.zeros(2))
        for i in range(len(P)):
            if tot[bat[i]] < minp:
                continue
            k = (bat[i], cells[d][i])
            n[k][par[i]] += 1
            s[k][par[i]] += loss[i]
        a = [s[k][0] / nn[0] for k, nn in n.items() if nn[0] >= 10 and nn[1] >= 10]
        b = [s[k][1] / nn[1] for k, nn in n.items() if nn[0] >= 10 and nn[1] >= 10]
        r = float(np.corrcoef(a, b)[0, 1]) if len(a) > 20 else float("nan")
        res[d] = 2 * r / (1 + r) if r > -1 else float("nan")
    return res


# ------------------------------------------------------------------ statistics

def cost_lift(S):
    """S: (..., 5) sums [flagged n, flagged excess sum, other n, other excess sum, flagged sum of squares]; returns runs per 100 pitches."""
    return -(S[..., 1] / S[..., 0] - S[..., 3] / S[..., 2]) * 100


class Tally:
    """Hitter-level and pair-level matrices for one shape, shared across paths so differences are paired."""

    def __init__(self, raw_out, paths, d):
        keys = {p: raw_out.get((p, d), {}) for p in paths}
        self.hitters = sorted({h for v in keys.values() for (h, _s) in v})
        self.starters = sorted({s for v in keys.values() for (_h, s) in v})
        hix = {h: i for i, h in enumerate(self.hitters)}
        six = {s: i for i, s in enumerate(self.starters)}
        self.H, self.pairs = {}, {}
        for p, v in keys.items():
            if not v:
                continue
            H = np.zeros((len(self.hitters), 5))
            hi, si, V = [], [], []
            for (h, s), vec in v.items():
                H[hix[h]] += vec
                hi.append(hix[h])
                si.append(six[s])
                V.append(vec)
            self.H[p] = H
            self.pairs[p] = (np.array(hi), np.array(si), np.array(V))

    def draws(self, rng, two_way=False):
        nh, ns = len(self.hitters), len(self.starters)
        Ch = np.stack([np.bincount(rng.integers(0, nh, nh), minlength=nh) for _ in range(NDRAW)]).astype(float)
        Cs = np.stack([np.bincount(rng.integers(0, ns, ns), minlength=ns) for _ in range(NDRAW)]).astype(float) if two_way else None
        return Ch, Cs

    def lifts(self, Ch, Cs=None):
        """Point estimates and bootstrap draws for every path. Hitter-only draws always; pigeonhole two-way draws when Cs is given."""
        out = {}
        for p, H in self.H.items():
            point = float(cost_lift(H.sum(0)))
            hd = cost_lift(Ch @ H)
            td = None
            if Cs is not None:
                hi, si, V = self.pairs[p]
                td = np.concatenate([cost_lift((Ch[i:i + CHUNK][:, hi] * Cs[i:i + CHUNK][:, si]) @ V) for i in range(0, NDRAW, CHUNK)])
            out[p] = (point, hd, td)
        return out


def ci(draws):
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi)


def pct(x):
    return f"{x:+.3f}"


# ------------------------------------------------------------------ stages

def make_context(a):
    t0 = time.time()
    rows, early, starters = rp.load(a.league, a.end)
    say(f"loaded {len(rows)} pitches ({time.time() - t0:.0f}s)")
    ok = lambda s: s.x_away is not None and s.z is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)
    swings = [s for s in rows if s.swing and ok(s)]
    takes = [s for s in rows if not s.swing]
    league = rp.ContactModel([], swings, mode="shapecount")
    zone = rp.CalledStrikeModel(takes)
    P = [s for s in rows if (s.game_pk, s.pitcher) in starters and ok(s) and (s.game_pk, s.at_bat, s.pitch_no) in early]
    P.sort(key=lambda s: (s.date, s.game_pk, s.at_bat, s.pitch_no))
    say(f"{len(P)} starter pitches ({time.time() - t0:.0f}s)")
    pred = predictions(league, zone, P, t0)
    loss, delta = losses(pred)
    say(f"mean loss {loss.mean() * 100:.2f} runs per 100 pitches ({time.time() - t0:.0f}s)")
    if a.check:
        l0, d0 = rp.referee(league, zone, P[:40000])
        say(f"CHECK against the Gate 0 referee on the first 40000 pitches: max |loss diff| {np.abs(l0 - loss[:40000]).max():.2e}, max |delta diff| {np.abs(d0 - delta[:40000]).max():.2e}")
    early_arr = np.array([early[(s.game_pk, s.at_bat, s.pitch_no)] for s in P])
    cells, ncell, isfb, fam, zr = rp.build_cells(P)
    third = (zr >= 1 / 3).astype(int) + (zr >= 2 / 3).astype(int)
    strat = (fam * 3 + third) * 12 + np.array([min(s.balls, 3) * 3 + min(s.strikes, 2) for s in P])
    return dict(P=P, pred=pred, loss=loss, delta=delta, early_arr=early_arr, cells=cells, ncell=ncell, isfb=isfb, fam=fam, strat=strat, t0=t0)


def roll(c, paths, loss=None, delta=None):
    raw_out = {}
    acc, touches, nstart, hb = rp.rolling(c["P"], c["loss"] if loss is None else loss, c["delta"] if delta is None else delta,
                                          c["early_arr"], c["cells"], c["ncell"], c["isfb"], c["fam"], rp.EVAL_START, paths, raw_out=raw_out, strat=c["strat"])
    return raw_out, acc, touches, nstart


def stage_v6(c, year):
    say(f"\nV6 {year}: two-way (hitter and starter) bootstrap on the raw-outcome cost lift, K = {rp.K_SHRINK:g}, {NDRAW} draws")
    raw_out, acc, touches, nstart = roll(c, BASE_PATHS)
    c["base_raw"] = raw_out
    rng = np.random.default_rng(101 + int(year))
    for d in DEFS:
        T = Tally(raw_out, BASE_PATHS, d)
        Ch, Cs = T.draws(rng, two_way=True)
        L = T.lifts(Ch, Cs)
        for p in ("L", "P", "E", "W", "U", "B1", "B3"):
            if p not in L:
                continue
            pt, hd, td = L[p]
            hl, hh = ci(hd)
            tl, th = ci(td)
            say(f"V6 {year} {d} {p}: lift {pct(pt)} hitter [{pct(hl)}, {pct(hh)}] two-way [{pct(tl)}, {pct(th)}] width ratio {(th - tl) / (hh - hl):.2f}  {'PASS' if tl > 0 else 'no'}")
        bl = [b for b in BASELINES if b in L]
        best = max(bl, key=lambda b: L[b][0])
        for p in ("P", "L", "E", "W"):
            if p not in L:
                continue
            dd, dt = L[p][1] - L[best][1], L[p][2] - L[best][2]
            pt = L[p][0] - L[best][0]
            hl, hh = ci(dd)
            tl, th = ci(dt)
            say(f"V6 {year} {d} {p} minus best baseline {best}: {pct(pt)} hitter [{pct(hl)}, {pct(hh)}] two-way [{pct(tl)}, {pct(th)}]  {'PASS' if tl > 0 else 'no'}")


def stage_v5(c, year):
    say(f"\nV5 {year}: shrinkage sweep, K in 10 20 40 80 160 ({NDRAW} hitter-cluster draws). P, E and the excess path use the same K.")
    rng = np.random.default_rng(202 + int(year))
    for k in (10, 20, 40, 80, 160):
        rp.K_SHRINK = float(k)
        raw_out, acc, touches, nstart = roll(c, ("L", "P", "E", "U"))
        for d in DEFS:
            T = Tally(raw_out, ("L", "P", "E", "U"), d)
            Ch, _ = T.draws(rng)
            L = T.lifts(Ch)
            cols = []
            for p in ("P", "E"):
                pt, hd, _ = L[p]
                lo, hi = ci(hd)
                cols.append(f"{p} {pct(pt)} [{pct(lo)}, {pct(hi)}] {'PASS' if lo > 0 else 'no'}")
            for p in ("L", "U"):
                dd = L["P"][1] - L[p][1]
                lo, hi = ci(dd)
                cols.append(f"P-{p} {pct(L['P'][0] - L[p][0])} [{pct(lo)}, {pct(hi)}] {'PASS' if lo > 0 else 'no'}")
            say(f"V5 {year} K={k} {d}: " + " | ".join(cols))
    rp.K_SHRINK = 40.0


def stage_v7(c, year):
    say(f"\nV7 {year}: Single-A style history caps, one factor at a time from the baseline (300 earlier hitter pitches, 2 earlier starter starts)")
    rng = np.random.default_rng(303 + int(year))
    settings = [(h, 2) for h in (100, 150, 200, 300)] + [(300, s) for s in (1, 3)]
    for hist, starts in settings:
        rp.MIN_HITTER_PITCHES, rp.MIN_STARTER_STARTS = hist, starts
        raw_out, acc, touches, nstart = roll(c, ("L", "P", "U"))
        rel = reliability_vals(c["P"], c["loss"], c["cells"], c["ncell"], hist)
        say(f"V7 {year} hist={hist} starts={starts}: hitter-starts {nstart}; B3 reliability " + ", ".join(f"{d} {rel[d]:+.2f}" for d in DEFS))
        for d in DEFS:
            T = Tally(raw_out, ("L", "P", "U"), d)
            Ch, _ = T.draws(rng)
            Lr = T.lifts(Ch)
            cols = []
            for p in ("P", "L", "U"):
                pt, hd, _ = Lr[p]
                lo, hi = ci(hd)
                cols.append(f"raw {p} {pct(pt)} [{pct(lo)}, {pct(hi)}] {'PASS' if lo > 0 else 'no'}")
            hs = {p: sorted(acc[(p, d)]) for p in ("P", "L") if acc.get((p, d))}
            if len(hs) == 2:
                common = sorted(set(hs["P"]) & set(hs["L"]))
                Mp = np.array([acc[("P", d)][h] for h in common])
                Ml = np.array([acc[("L", d)][h] for h in common])
                diffs = []
                for _ in range(NDRAW):
                    i = rng.integers(0, len(common), len(common))
                    diffs.append(rp.b1(Mp[i]) - rp.b1(Ml[i]))
                lo, hi = ci(diffs)
                cols.append(f"model B1 P {rp.b1(Mp):.2f} L {rp.b1(Ml):.2f}, B2 P-L {rp.b1(Mp) - rp.b1(Ml):+.3f} [{lo:+.3f}, {hi:+.3f}] {'PASS' if lo > 0 else 'no'}")
            fl = {p: float(np.mean(touches[(p, d)])) if touches.get((p, d)) else 0.0 for p in ("P", "L")}
            say(f"V7 {year} hist={hist} starts={starts} {d}: flagged per start P {fl['P']:.1f} L {fl['L']:.1f} | " + " | ".join(cols))
    rp.MIN_HITTER_PITCHES, rp.MIN_STARTER_STARTS = 300, 2


def stage_v9(c, year):
    say(f"\nV9 {year}: hitter-specific referee (out-of-fold whiff and contact-quality shifts), full rerun of the raw-outcome tally")
    w, x = hitter_shifts(c["P"], c["pred"])
    loss9, delta9 = losses(c["pred"], w, x)
    say(f"whiff logit shift sd {w.std():.3f}, contact-quality shift sd {x.std():.3f}; mean loss {loss9.mean() * 100:.2f} vs {c['loss'].mean() * 100:.2f} runs per 100 pitches; correlation of pitch losses {np.corrcoef(loss9, c['loss'])[0, 1]:.3f}")
    paths = ("L", "P", "E", "W", "U")
    raw9, _, _, nstart = roll(c, paths, loss9, delta9)
    rawb = c.get("base_raw")
    if rawb is None:
        rawb, _, _, _ = roll(c, paths)
    rng = np.random.default_rng(404 + int(year))
    for d in DEFS:
        T9, Tb = Tally(raw9, paths, d), Tally(rawb, paths, d)
        Ch9, _ = T9.draws(rng)
        Chb, _ = Tb.draws(rng)
        L9, Lb = T9.lifts(Ch9), Tb.lifts(Chb)
        for p in paths:
            pt, hd, _ = L9[p]
            lo, hi = ci(hd)
            ob = Lb[p][0]
            say(f"V9 {year} {d} {p}: hitter-specific referee lift {pct(pt)} [{pct(lo)}, {pct(hi)}] {'PASS' if lo > 0 else 'no'} (original referee {pct(ob)})")
        for p in ("P", "L", "E", "W"):
            bl = [b for b in ("U",) if b in L9]
            dd = L9[p][1] - L9["U"][1]
            lo, hi = ci(dd)
            say(f"V9 {year} {d} {p} minus U: {pct(L9[p][0] - L9['U'][0])} [{pct(lo)}, {pct(hi)}] {'PASS' if lo > 0 else 'no'}")


def stage_v7b(c, year):
    say(f"\nV7b {year}: Single-A style curve by exact history size. Each hitter-start is tallied by how many earlier pitches the hitter had at that point.")
    edges = (200, 300, 500)
    labels = ("100-199", "200-299", "300-499", "500+")
    rp.MIN_HITTER_PITCHES = 100
    raw_out = {}
    acc, touches, nstart, hb = rp.rolling(c["P"], c["loss"], c["delta"], c["early_arr"], c["cells"], c["ncell"], c["isfb"], c["fam"], rp.EVAL_START,
                                          ("L", "P", "U"), raw_out=raw_out, strat=c["strat"], hist_edges=edges)
    rp.MIN_HITTER_PITCHES = 300
    rng = np.random.default_rng(505 + int(year))
    say(f"hitter-starts evaluated with 100+ earlier pitches: {nstart}")
    for bi, lab in enumerate(labels):
        for d in DEFS:
            sub = {(p, dd): v for (p, dd, b), v in raw_out.items() if b == bi and dd == d}
            if not sub:
                continue
            T = Tally(sub, ("L", "P", "U"), d)
            Ch, _ = T.draws(rng)
            Lr = T.lifts(Ch)
            n = int(T.H["P"][:, 0].sum() + T.H["P"][:, 2].sum()) if "P" in T.H else 0
            cols = []
            for p in ("P", "L", "U"):
                if p not in Lr:
                    continue
                pt, hd, _ = Lr[p]
                lo, hi = ci(hd)
                cols.append(f"{p} {pct(pt)} [{pct(lo)}, {pct(hi)}] {'PASS' if lo > 0 else 'no'}")
            if "P" in Lr and "L" in Lr:
                dd = Lr["P"][1] - Lr["L"][1]
                lo, hi = ci(dd)
                cols.append(f"P-L {pct(Lr['P'][0] - Lr['L'][0])} [{pct(lo)}, {pct(hi)}] {'PASS' if lo > 0 else 'no'}")
            say(f"V7b {year} history {lab} {d}: pitches {n} | " + " | ".join(cols))


STAGES = (("v6", stage_v6), ("v5", stage_v5), ("v7", stage_v7), ("v9", stage_v9), ("v7b", stage_v7b))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--year", required=True)
    ap.add_argument("--end", default=None)
    ap.add_argument("--check", action="store_true", help="smoke test: compare the rebuilt referee with the Gate 0 referee")
    ap.add_argument("--out-dir", default="docs")
    ap.add_argument("--stages", default="v6,v5,v7,v9,v7b")
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    rp.EVAL_START = f"{a.year}-05-01"
    out_dir = pathlib.Path(a.out_dir)
    todo = [(n, f) for n, f in STAGES if n in a.stages.split(",") and not (out_dir / f"validation_results_{n}_{a.year}{a.tag}.txt").exists()]
    if not todo:
        say("all requested stages already have result files")
        return 0
    say(f"Validation suite {a.year}: league {a.league}, stages {','.join(n for n, _ in todo)}")
    c = make_context(a)
    for name, fn in todo:
        _OUT.clear()
        t = time.time()
        fn(c, a.year)
        say(f"stage {name} time {time.time() - t:.0f}s")
        (out_dir / f"validation_results_{name}_{a.year}{a.tag}.txt").write_text("\n".join(_OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
