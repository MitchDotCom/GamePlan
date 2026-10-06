"""Gate 0: three candidate ways to choose a hitter's two focus pitches against tonight's starter (docs/GATE0_PREREGISTRATION.md, addendum).

  P  personal      starter usage x this hitter's earlier loss on the pitch (shrunk toward the league, K = 40)
  L  starter-level starter usage x the league's loss on the pitch (same calls for every hitter)
  D  look-alike    non-fastball pitches ranked by usage x league loss x closeness to the starter's fastball path early in flight

Rolling: every call for a hitter-start uses only earlier games. "Loss" is the runs lost against the better option under the average-hitter
model (the referee, fit on the full season, which defines truth and is never used to pick a call). Also runs the direct look-alike test.

    python -m gameplan.recognition_paths --league data/league --eval-start 2025-05-01 --split 2025-07-01 --out docs/gate0_results_2025.txt"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import math
import pathlib
import time
from collections import defaultdict
from types import SimpleNamespace

import numpy as np

from .coach import FAMILY_OF
from .constants import value as _const
from .decision import evs_np
from .plane_fit import _boot, _logloss, _sigmoid, fit_logit
from .savant import parse_swings
from .shape import ContactModel
from .zone import CalledStrikeModel

SCALE = _const("WOBA_SCALE_2025")
K_SHRINK = 40.0
MIN_HITTER_PITCHES = 300
MIN_STARTER_STARTS = 2
MIN_STARTER_FB = 20
Y_TUNNEL = 23.8            # feet from the plate where early-flight position is read
SEP_SCALE = 0.5            # feet; closeness = 1 / (1 + separation / SEP_SCALE)
SIDE_CUT = 0.28
BOOT = 1000
SEED = 17
DEFS = ("S1", "S2", "S3", "S4")
PATHS = ("P", "L", "D")
FAM_IDX = {"FB": 0, "BRK": 1, "OFF": 2, "OTH": 3}
_OUT: list[str] = []


def say(msg: str = "") -> None:
    print(msg, flush=True)
    _OUT.append(msg)


# ------------------------------------------------------------------ loading

def _tt(vy: float, ay: float, y_target: float) -> float | None:
    c = 50.0 - y_target
    disc = vy * vy - 2.0 * ay * c
    if ay == 0 or disc < 0:
        return None
    return (-vy - math.sqrt(disc)) / ay


def early_xz(r: dict):
    """Position (x, z) when the pitch is Y_TUNNEL feet from the plate, from the Statcast trajectory and the plate location."""
    try:
        vx, vy, vz, ax, ay, az = (float(r[k]) for k in ("vx0", "vy0", "vz0", "ax", "ay", "az"))
        px, pz = float(r["plate_x"]), float(r["plate_z"])
    except (KeyError, TypeError, ValueError):
        return None
    big_t, t = _tt(vy, ay, 17.0 / 12.0), _tt(vy, ay, Y_TUNNEL)
    if big_t is None or t is None:
        return None
    dt, dt2 = big_t - t, big_t * big_t - t * t
    return px - vx * dt - 0.5 * ax * dt2, pz - vz * dt - 0.5 * az * dt2


def load(league_dir: str, end: str | None = None):
    rows, early, first = [], {}, {}
    for f in sorted(glob.glob(str(pathlib.Path(league_dir) / "*.csv"))):
        if end and pathlib.Path(f).stem > end:
            break
        text = open(f, encoding="utf-8-sig").read()
        rows += parse_swings(text, include_takes=True)
        for r in csv.DictReader(io.StringIO(text)):
            try:
                ab, pn = int(float(r["at_bat_number"])), int(float(r["pitch_number"]))
            except (KeyError, ValueError):
                continue
            k = (r["game_pk"], r["inning_topbot"])
            if k not in first or ab < first[k][0]:
                first[k] = (ab, r["pitcher"])
            e = early_xz(r)
            if e is not None:
                early[(r["game_pk"], ab, pn)] = e
    starters = {(gk, p) for (gk, _), (_, p) in first.items()}
    return rows, early, starters


def referee(league, zone, rows):
    """(loss, delta) per pitch in runs: loss = better option minus what he did, delta = swing minus take, both under the average-hitter model."""
    Q, mask = league.query_swings(rows)
    assert mask.all()
    p = league.predict(Q, use_hitter=False)
    sb = np.array([s.sz_bot or 1.5 for s in rows])
    st = np.array([s.sz_top or 3.5 for s in rows])
    bal = np.array([s.balls for s in rows])
    stk = np.array([s.strikes for s in rows])
    p_cs = zone.p(Q[:, 0], Q[:, 1], sb, st, strikes=stk, balls=bal)
    sw, tk = evs_np(p["whiff"], p["foul"], p["xw"], p_cs, bal, stk)
    swung = np.array([s.swing for s in rows])
    loss = np.maximum(np.maximum(sw, tk) - np.where(swung, sw, tk), 0.0) / SCALE
    return loss, (sw - tk) / SCALE


def kmeans(X, k=8, iters=25, seed=3):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(2), axis=1)
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return C


def build_cells(P):
    fam = np.array([FAM_IDX.get(FAMILY_OF.get(s.pitch_type, "OTH"), 3) for s in P])
    sb = np.array([s.sz_bot or 1.5 for s in P])
    st = np.array([s.sz_top or 3.5 for s in P])
    z = np.array([s.z for s in P])
    xa = np.array([s.x_away for s in P])
    zr = (z - sb) / np.maximum(st - sb, 0.5)
    third = (zr >= 1 / 3).astype(int) + (zr >= 2 / 3).astype(int)
    side = (xa >= -SIDE_CUT).astype(int) + (xa > SIDE_CUT).astype(int)
    types = sorted({s.pitch_type for s in P})
    tix = {t: i for i, t in enumerate(types)}
    tcode = np.array([tix[s.pitch_type] for s in P])
    X = np.array([[s.velo, s.ivb, s.hb, s.vaa] for s in P], float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    sample = Z[np.random.default_rng(5).choice(len(Z), min(100000, len(Z)), replace=False)]
    C = kmeans(sample)
    clus = np.concatenate([np.argmin(((Z[i:i + 50000, None, :] - C[None]) ** 2).sum(2), axis=1) for i in range(0, len(Z), 50000)])
    cells = {"S1": fam * 3 + third, "S2": (fam * 3 + third) * 3 + side, "S3": tcode * 3 + third, "S4": clus * 3 + third}
    ncell = {"S1": 12, "S2": 36, "S3": len(types) * 3, "S4": 24}
    isfb = {}
    for d in DEFS:
        frac = np.zeros(ncell[d])
        n = np.bincount(cells[d], minlength=ncell[d])
        fb = np.bincount(cells[d], weights=(fam == 0).astype(float), minlength=ncell[d])
        frac[n > 0] = fb[n > 0] / n[n > 0]
        isfb[d] = frac > 0.5
    return cells, ncell, isfb, fam, zr


# ------------------------------------------------------------------ rolling evaluation

def _pick_take_swing(score, usage, take):
    out = []
    for m in (take, ~take):
        sc = np.where(m & (usage > 0), score, -np.inf)
        j = int(np.argmax(sc))
        if np.isfinite(sc[j]):
            out.append(j)
    return out


def _pick_top2(score):
    j = np.argsort(-score)[:2]
    return [int(i) for i in j if np.isfinite(score[i]) and score[i] > 0]


def rolling(P, loss, delta, early_arr, cells, ncell, isfb, fam, eval_start, paths=PATHS, raw_out=None, strat=None):
    """raw_out (dict) switches on the validation-plan V1/V2 tally: for each path and shape, per hitter
    [flagged n, flagged sum, other n, other sum, flagged sum of squares] of his raw run value (Statcast delta_run_exp, hitter side)
    minus the earlier-games league mean for the same stratum (strat). Paths B1 and B3 are the naive baselines."""
    dates = np.array([s.date for s in P])
    game = np.array([s.game_pk for s in P])
    pit = np.array([s.pitcher for s in P])
    bat = np.array([s.batter for s in P])
    order = np.argsort(dates, kind="stable")
    league = {d: [np.zeros(ncell[d]), np.zeros(ncell[d]), np.zeros(ncell[d])] for d in DEFS}   # n, loss sum, delta sum
    hit = {d: defaultdict(lambda n=ncell[d]: [np.zeros(n), np.zeros(n)]) for d in DEFS}
    sta = {d: defaultdict(lambda n=ncell[d]: [np.zeros(n), np.zeros(n), np.zeros(n)]) for d in DEFS}   # n, sum x, sum z
    fbs = defaultdict(lambda: np.zeros(3))
    starts = defaultdict(set)
    hp = defaultdict(int)
    acc = {(p, d): defaultdict(lambda: np.zeros(8)) for p in paths for d in DEFS}
    touches = {(p, d): [] for p in paths for d in DEFS}
    hb = {(p, d): [0, 0] for p in paths for d in DEFS}      # calls, calls on cells where his shrunk loss is at or below the league's
    nstart = 0
    raw = np.array([np.nan if s.run_exp is None else s.run_exp for s in P]) if raw_out is not None else None
    rawexc = np.full(len(P), np.nan)
    sl_n, sl_s = np.zeros(144), np.zeros(144)               # league raw run value by stratum, earlier games only
    hr = defaultdict(lambda: {d: [np.zeros(ncell[d]), np.zeros(ncell[d])] for d in DEFS})   # his raw excess by cell: n, sum
    uniq = sorted(set(dates[order]))
    pos = {d: [] for d in uniq}
    for i in order:
        pos[dates[i]].append(i)
    t0 = time.time()
    for day_no, day in enumerate(uniq):
        idx = np.array(pos[day])
        if raw is not None:
            sm = np.where(sl_n > 0, sl_s / np.maximum(sl_n, 1), 0.0)
            rawexc[idx] = raw[idx] - sm[strat[idx]]
        groups = defaultdict(list)
        for i in idx:
            groups[(game[i], pit[i], bat[i])].append(i)
        if day >= eval_start:
            for (g, p, b), gi in groups.items():
                if hp[b] < MIN_HITTER_PITCHES or len(starts[p]) < MIN_STARTER_STARTS or fbs[p][0] < MIN_STARTER_FB:
                    continue
                gi = np.array(gi)
                nstart += 1
                fx, fz = fbs[p][1] / fbs[p][0], fbs[p][2] / fbs[p][0]
                for d in DEFS:
                    Ln, Ls, Ld = league[d]
                    if Ln.sum() == 0:
                        continue
                    gmean = Ls.sum() / Ln.sum()
                    Lm = np.where(Ln > 0, Ls / np.maximum(Ln, 1), gmean)
                    Dm = np.where(Ln > 0, Ld / np.maximum(Ln, 1), 0.0)
                    sn, sx, sz = sta[d][p]
                    if sn.sum() == 0:
                        continue
                    usage = sn / sn.sum()
                    hn, hs = hit[d][b]
                    Hm = (hs + K_SHRINK * Lm) / (hn + K_SHRINK)
                    take = Dm < 0
                    sep = np.where(sn > 0, np.hypot(sx / np.maximum(sn, 1) - fx, sz / np.maximum(sn, 1) - fz), np.inf)
                    w = np.where(np.isfinite(sep), 1.0 / (1.0 + sep / SEP_SCALE), 0.0)
                    focus = {"P": _pick_take_swing(usage * Hm, usage, take), "L": _pick_take_swing(usage * Lm, usage, take),
                             "D": _pick_top2(np.where(~isfb[d] & (usage > 0), usage * Lm * w, -np.inf))}
                    excess = Hm - Lm
                    okn = hn >= 10
                    if "E" in paths:       # addendum 2: usage x his excess loss over the league, only where he is worse than the league
                        focus["E"] = _pick_take_swing(np.where(okn & (excess > 0) & (usage > 0), usage * excess, -np.inf), usage, take)
                    if "W" in paths:       # addendum 2: his standing weak spots (excess loss alone) on pitches the starter throws at least 5% of the time
                        focus["W"] = _pick_take_swing(np.where(okn & (excess > 0) & (usage >= 0.05), excess, -np.inf), usage, take)
                    if "U" in paths:       # post-hoc control: the starter's most-used take cell and swing cell, ignoring loss
                        focus["U"] = _pick_take_swing(usage, usage, take)
                    if "N" in paths:       # post-hoc control: D without the closeness weight (non-fastball cells by usage x league loss)
                        focus["N"] = _pick_top2(np.where(~isfb[d] & (usage > 0), usage * Lm, -np.inf))
                    if raw_out is not None:
                        rn, rs = hr[b][d]
                        Rm = -(rs / (rn + K_SHRINK))            # his shrunk cost per pitch in each cell (positive = he loses runs there)
                        okr = rn >= 10
                        if "B1" in paths:    # baseline 1: his two costliest cells to date, ignoring the starter
                            sc = np.where(okr & (Rm > 0), Rm, -np.inf)
                            focus["B1"] = [int(j) for j in np.argsort(-sc)[:2] if np.isfinite(sc[j])]
                        if "B3" in paths:    # baseline 3: his costliest cell plus the starter's most-used non-fastball cell
                            sc = np.where(okr & (Rm > 0), Rm, -np.inf)
                            j1 = int(np.argmax(sc))
                            us = np.where(~isfb[d] & (usage > 0), usage, -np.inf)
                            j2 = int(np.argmax(us))
                            focus["B3"] = ([j1] if np.isfinite(sc[j1]) else []) + ([j2] if np.isfinite(us[j2]) else [])
                    cg, lg = cells[d][gi], loss[gi]
                    exc = lg - Lm[cg]          # his loss on each pitch minus the league's average loss on that kind of pitch (post-hoc excess measure)
                    for path, fc in focus.items():
                        if not fc or path not in paths:
                            continue
                        m = np.isin(cg, fc)
                        hb[(path, d)][0] += len(fc)
                        hb[(path, d)][1] += int(sum(1 for j in fc if Hm[j] <= Lm[j]))
                        a = acc[(path, d)][b]
                        a += (m.sum(), lg[m].sum(), (~m).sum(), lg[~m].sum(), len(gi), lg.sum(), exc[m].sum(), exc[~m].sum())
                        touches[(path, d)].append(int(m.sum()))
                        if raw_out is not None:
                            xr = rawexc[gi]
                            ok = ~np.isnan(xr)
                            fm, um = m & ok, ~m & ok
                            ra = raw_out.setdefault((path, d), defaultdict(lambda: np.zeros(5)))[b]
                            ra += (fm.sum(), xr[fm].sum(), um.sum(), xr[um].sum(), (xr[fm] ** 2).sum())
        # update stats with today's pitches
        if raw is not None:
            ok = ~np.isnan(rawexc[idx])
            np.add.at(sl_n, strat[idx][ok], 1)
            np.add.at(sl_s, strat[idx][ok], raw[idx][ok])
        for d in DEFS:
            c = cells[d][idx]
            np.add.at(league[d][0], c, 1)
            np.add.at(league[d][1], c, loss[idx])
            np.add.at(league[d][2], c, delta[idx])
        for (g, p, b), gi in groups.items():
            gi = np.array(gi)
            hp[b] += len(gi)
            starts[p].add(day)
            ex, ez = early_arr[gi, 0], early_arr[gi, 1]
            isf = fam[gi] == 0
            fbs[p] += (isf.sum(), ex[isf].sum(), ez[isf].sum())
            for d in DEFS:
                c = cells[d][gi]
                np.add.at(hit[d][b][0], c, 1)
                np.add.at(hit[d][b][1], c, loss[gi])
                if raw is not None:
                    okg = ~np.isnan(rawexc[gi])
                    np.add.at(hr[b][d][0], c[okg], 1)
                    np.add.at(hr[b][d][1], c[okg], rawexc[gi][okg])
                np.add.at(sta[d][p][0], c, 1)
                np.add.at(sta[d][p][1], c, ex)
                np.add.at(sta[d][p][2], c, ez)
        if day_no % 20 == 0:
            say(f"  rolling {day} ({day_no + 1}/{len(uniq)}), hitter-starts evaluated so far {nstart}, {time.time() - t0:.0f}s")
    return acc, touches, nstart, hb


def b1(M):
    return (M[:, 1].sum() / M[:, 0].sum()) / (M[:, 3].sum() / M[:, 2].sum())


def report_paths(acc, touches, nstart, paths=PATHS, b2=True):
    rng = np.random.default_rng(SEED)
    say(f"\nHitter-starts evaluated: {nstart}")
    mats = {}
    for k, v in acc.items():
        if v:
            mats[k] = (sorted(v), np.array([v[h] for h in sorted(v)]))
    say("\nTEST A (coverage), B1 (real weak spot), C (concentration). B1 = loss per pitch on focus cells / loss per pitch on his other cells.")
    say(f"{'def':4s} {'path':4s} {'hitter-starts':>13s} {'median touches':>14s} {'mean':>6s} {'zero share':>10s}  {'B1 lift [95% CI]':>22s}  {'loss share':>10s} {'pitch share':>11s}  A / B1 / C")
    boots = {}
    for d in DEFS:
        for p in paths:
            if (p, d) not in mats:
                continue
            hs, M = mats[(p, d)]
            t = np.array(touches[(p, d)])
            lift = b1(M)
            bs = []
            for _ in range(BOOT):
                i = rng.integers(0, len(M), len(M))
                bs.append(b1(M[i]))
            boots[(p, d)] = (hs, M, np.array(bs))
            lo, hi = np.percentile(bs, [2.5, 97.5])
            lshare, pshare = M[:, 1].sum() / M[:, 5].sum(), M[:, 0].sum() / M[:, 4].sum()
            med = float(np.median(t))
            a = "PASS" if med >= 2.0 else "WIDEN" if med >= 1.0 else "FAIL"
            b = "PASS" if (lift >= 1.25 and lo > 1.0) else "no"
            c = "PASS" if (lshare >= 0.30 and lshare >= 1.5 * pshare) else "no"
            say(f"{d:4s} {p:4s} {len(t):13d} {med:14.1f} {t.mean():6.2f} {(t == 0).mean():10.2f}  {lift:7.2f} [{lo:5.2f}, {hi:5.2f}] {lshare:10.3f} {pshare:11.3f}  {a} / {b} / {c}")
    if not b2:
        return
    say("\nTEST B2 (is it him): B1 of P minus B1 of L, same hitters, same resamples. PASS = lower bound above 0.")
    for d in DEFS:
        if ("P", d) in mats and ("L", d) in mats:
            hp_, Mp = mats[("P", d)]
            hl_, Ml = mats[("L", d)]
            common = sorted(set(hp_) & set(hl_))
            ip = [hp_.index(h) for h in common]
            il = [hl_.index(h) for h in common]
            Mp, Ml = Mp[ip], Ml[il]
            diff = b1(Mp) - b1(Ml)
            bs = []
            r2 = np.random.default_rng(SEED + 1)
            for _ in range(BOOT):
                i = r2.integers(0, len(Mp), len(Mp))
                bs.append(b1(Mp[i]) - b1(Ml[i]))
            lo, hi = np.percentile(bs, [2.5, 97.5])
            say(f"{d}: P {b1(Mp):.3f} - L {b1(Ml):.3f} = {diff:+.3f} [{lo:+.3f}, {hi:+.3f}]  {'PASS' if lo > 0 else 'no'}  ({len(common)} hitters)")


def report_excess(acc, touches, nstart, hb):
    rng = np.random.default_rng(SEED + 2)
    mats = {k: (sorted(v), np.array([v[h] for h in sorted(v)])) for k, v in acc.items() if v}
    say("\nADDENDUM 2: share of hitter-starts that get a call, share of calls on pitches he handles at least as well as the league, and B2 against the starter-level ranking (L).")
    for d in DEFS:
        for p in ("P", "E", "W", "L"):
            if (p, d) not in mats:
                continue
            c, h = hb[(p, d)]
            say(f"{d} {p}: flagged {len(touches[(p, d)]) / nstart * 100:5.1f}% of hitter-starts; calls on pitches he handles at least as well as the league {h / max(c, 1) * 100:5.1f}%")
        for p in ("P", "E", "W"):
            if (p, d) not in mats or ("L", d) not in mats:
                continue
            hp_, Mp = mats[(p, d)]
            hl_, Ml = mats[("L", d)]
            common = sorted(set(hp_) & set(hl_))
            Mp, Ml = Mp[[hp_.index(h) for h in common]], Ml[[hl_.index(h) for h in common]]
            bs = []
            for _ in range(BOOT):
                i = rng.integers(0, len(Mp), len(Mp))
                bs.append(b1(Mp[i]) - b1(Ml[i]))
            lo, hi = np.percentile(bs, [2.5, 97.5])
            say(f"{d} B2 {p} minus L: {b1(Mp):.3f} - {b1(Ml):.3f} = {b1(Mp) - b1(Ml):+.3f} [{lo:+.3f}, {hi:+.3f}]  {'PASS' if lo > 0 else 'no'}  ({len(common)} hitters)")


def report_excess_lift(acc, hb=None):
    """Post-hoc (not pre-registered): do the flagged pitches cost HIM more than they cost other hitters on the same kind of pitch?
    Excess lift = his mean excess loss on the called pitches minus on his other pitches, in runs per 100 pitches."""
    rng = np.random.default_rng(SEED + 3)
    say("\nPOST-HOC EXCESS LIFT (runs per 100 pitches; positive = the flagged pitches cost him more than the league on the same kind of pitch)")
    def lift(M):
        return (M[:, 6].sum() / M[:, 0].sum() - M[:, 7].sum() / M[:, 2].sum()) * 100
    for d in DEFS:
        for p in ("P", "E", "W", "L"):
            v = acc.get((p, d))
            if not v:
                continue
            M = np.array([v[h] for h in sorted(v)])
            bs = [lift(M[rng.integers(0, len(M), len(M))]) for _ in range(BOOT)]
            lo, hi = np.percentile(bs, [2.5, 97.5])
            say(f"{d} {p}: excess lift {lift(M):+.3f} [{lo:+.3f}, {hi:+.3f}]  {'PASS' if lo > 0 else 'no'}")


def report_raw(raw_out, touches, paths):
    """Validation plan V1 (raw outcome), V2 (naive baselines), V3 (effect size). Cost lift = how many more runs per 100 pitches the flagged
    pitches cost him than his other pitches, in actual Statcast run value net of the earlier-games league mean for the same kind of pitch."""
    rng = np.random.default_rng(SEED + 5)
    base = [b for b in ("B1", "B3", "U") if b in paths]
    def lift(M):
        return -(M[:, 1].sum() / M[:, 0].sum() - M[:, 3].sum() / M[:, 2].sum()) * 100
    say("\nV1 RAW-OUTCOME COST LIFT (runs per 100 pitches; positive = the flagged pitches cost him more in actual run value; bar: interval above 0)")
    boots = {}
    for d in DEFS:
        mats = {}
        for p in paths:
            v = raw_out.get((p, d))
            if v:
                mats[p] = {h: v[h] for h in v}
        if not mats:
            continue
        hitters = sorted(set().union(*[set(m) for m in mats.values()]))
        zero = np.zeros(5)
        full = {p: np.array([m.get(h, zero) for h in hitters]) for p, m in mats.items()}
        draws = [rng.integers(0, len(hitters), len(hitters)) for _ in range(BOOT)]
        for p, M in full.items():
            bs = np.array([lift(M[ix]) for ix in draws])
            lo, hi = np.percentile(bs, [2.5, 97.5])
            boots[(p, d)] = bs
            say(f"{d} {p}: cost lift {lift(M):+.3f} [{lo:+.3f}, {hi:+.3f}]  {'PASS' if lo > 0 else 'no'}   (flagged pitches {int(M[:, 0].sum())})")
        say(f"V2 {d}: model paths vs the best naive baseline (difference in cost lift; bar: interval above 0 and at least 25% larger)")
        bl = [b for b in base if b in full]
        if not bl:
            continue
        best = max(bl, key=lambda b: lift(full[b]))
        for p in ("P", "L", "E", "W"):
            if p not in full:
                continue
            diff = np.array([lift(full[p][ix]) - lift(full[best][ix]) for ix in draws])
            lo, hi = np.percentile(diff, [2.5, 97.5])
            rel = lift(full[p]) / lift(full[best]) - 1 if lift(full[best]) > 0 else float("nan")
            say(f"{d} {p} vs best baseline {best}: {lift(full[p]) - lift(full[best]):+.3f} [{lo:+.3f}, {hi:+.3f}], relative {rel:+.0%}  {'PASS' if lo > 0 and rel >= 0.25 else 'no'}")
        for p in ("P", "L", "E", "W"):
            if p not in full:
                continue
            M = full[p]
            tl = touches[(p, d)]
            per_start = float(np.mean(tl)) if tl else 0.0
            lf = lift(M)
            n_f = M[:, 0].sum()
            mf = M[:, 1].sum() / n_f
            sd = math.sqrt(max(M[:, 4].sum() / n_f - mf * mf, 0.0))
            need = (2.8 * sd / (lf / 100)) ** 2 if lf > 0 else float("inf")
            say(f"V3 {d} {p}: {per_start:.1f} flagged pitches per start; {lf / 100 * per_start:+.3f} runs per hitter-start; about {lf / 100 * per_start * 150:+.1f} runs per hitter over 150 starts; "
                f"games to detect it in one hitter at 80% power: {need / max(per_start, 1e-9):,.0f}")


def reliability(P, loss, cells, ncell):
    bat = np.array([s.batter for s in P])
    date_game = [(s.date, s.game_pk) for s in P]
    order = sorted(range(len(P)), key=lambda i: date_game[i])
    ordinal, seen_games = {}, defaultdict(dict)
    par = np.zeros(len(P), int)
    for i in order:
        b, gk = bat[i], date_game[i][1]
        g = seen_games[b]
        if gk not in g:
            g[gk] = len(g)
        par[i] = g[gk] % 2
    say("\nTEST B3 (reliability): odd-game vs even-game mean loss per (hitter, cell), cells with at least 10 pitches in each half, hitters with 300+ pitches. Spearman-Brown corrected. PASS >= 0.40")
    tot = defaultdict(int)
    for b in bat:
        tot[b] += 1
    for d in DEFS:
        n = defaultdict(lambda: np.zeros(2))
        s = defaultdict(lambda: np.zeros(2))
        for i in range(len(P)):
            if tot[bat[i]] < MIN_HITTER_PITCHES:
                continue
            k = (bat[i], cells[d][i])
            n[k][par[i]] += 1
            s[k][par[i]] += loss[i]
        a, b = [], []
        for k, nn in n.items():
            if nn[0] >= 10 and nn[1] >= 10:
                a.append(s[k][0] / nn[0])
                b.append(s[k][1] / nn[1])
        r = float(np.corrcoef(a, b)[0, 1]) if len(a) > 20 else float("nan")
        sb = 2 * r / (1 + r) if r > -1 else float("nan")
        say(f"{d}: {len(a)} hitter-cells, split-half r {r:+.3f}, corrected {sb:+.3f}  {'PASS' if sb >= 0.4 else 'no'}")


# ------------------------------------------------------------------ direct look-alike test

def direct_test(P, early_arr, fam, zr, split, matched=False):
    say("\nD-DIRECT: does early-flight closeness to the starter's fastball predict more whiffs / chase, after controls? Non-fastball pitches; fit before the split date, scored after.")
    dates = np.array([s.date for s in P])
    pit = np.array([s.pitcher for s in P])
    bat = np.array([s.batter for s in P])
    train = dates < split
    fbm = {}
    for p in set(pit[train & (fam == 0)]):
        m = train & (fam == 0) & (pit == p)
        if m.sum() >= 30:
            fbm[p] = early_arr[m].mean(0)
    keep = np.array([(fam[i] in (1, 2)) and (pit[i] in fbm) for i in range(len(P))])
    idx = np.where(keep)[0]
    if matched:
        # expected early position of THIS pitcher's fastball that ends at this pitch's plate location (linear in plate x and z, fit on his
        # training-period fastballs): separation then measures same endpoint, different early path
        reg = {}
        for p in fbm:
            m = train & (fam == 0) & (pit == p)
            A = np.column_stack([np.ones(m.sum()), [P[i].x for i in np.where(m)[0]], [P[i].z for i in np.where(m)[0]]])
            reg[p] = np.linalg.lstsq(A, early_arr[m], rcond=None)[0]
        sep = np.array([math.hypot(*(early_arr[i] - np.array([1.0, P[i].x, P[i].z]) @ reg[pit[i]])) for i in idx])
    else:
        sep = np.array([math.hypot(early_arr[i, 0] - fbm[pit[i]][0], early_arr[i, 1] - fbm[pit[i]][1]) for i in idx])
    pitchers = {p: j for j, p in enumerate(sorted(set(pit[idx])))}
    gi = np.array([pitchers[pit[i]] for i in idx])
    S = [P[i] for i in idx]
    xa = np.array([s.x_away for s in S])
    zz = zr[idx]
    cols = [np.ones(len(S)), (fam[idx] == 2).astype(float), xa, xa ** 2, zz, zz ** 2, np.array([(s.velo - 90) / 5 for s in S]),
            np.array([s.ivb / 12 for s in S]), np.array([s.hb / 12 for s in S]), np.array([(s.vaa + 6) / 2 for s in S]),
            np.array([float(s.strikes == 1) for s in S]), np.array([float(s.strikes == 2) for s in S]), np.array([float(s.balls >= 2) for s in S])]
    X0 = np.column_stack(cols)
    tr = dates[idx] < split
    te = ~tr
    sep_z = (sep - sep[tr].mean()) / (sep[tr].std() + 1e-9)
    X1 = np.column_stack([X0, sep_z])
    swing = np.array([float(s.swing) for s in S])
    whiff = np.array([float(s.whiff) for s in S])
    ooz = (np.abs(xa) > 0.83) | (zz < 0) | (zz > 1)
    bats = np.array([bat[i] for i in idx])
    for name, sel, y in (("whiff per swing", swing == 1, whiff), ("chase (swing at out-of-zone pitches)", ooz, swing)):
        a, b = sel & tr, sel & te
        res = {}
        for lab, X in (("base", X0), ("+sep", X1)):
            beta, off = fit_logit(X[a], y[a], gi[a], len(pitchers))
            mu = _sigmoid(X[b] @ beta + off[gi[b]])
            res[lab] = (_logloss(y[b], mu), beta)
        gain, lo, hi = _boot(list(bats[b]), res["base"][0] - res["+sep"][0])
        coef = res["+sep"][1][-1]
        say(f"{name}: {a.sum()} train, {b.sum()} test; log-loss gain per pitch {gain:+.5f} [{lo:+.5f}, {hi:+.5f}]; coefficient on separation (standardized) {coef:+.4f} "
            f"({'closer to the fastball path = more ' + ('whiffs' if 'whiff' in name else 'chase') if coef < 0 else 'farther = more'})  "
            f"{'PASS' if (lo > 0 and coef < 0) else 'no'}")


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    global MIN_HITTER_PITCHES
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--eval-start", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--end", default=None, help="last day to load (quick tests)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-hitter-pitches", type=int, default=MIN_HITTER_PITCHES, help="earlier pitches a hitter needs before his calls count (150 for the Single-A-size stress test)")
    ap.add_argument("--excess", action="store_true", help="addendum 2: paths L, P, E (excess loss) and W (standing weak spots)")
    ap.add_argument("--raw", action="store_true", help="validation plan V1 to V3: raw run value, naive baselines, effect size")
    ap.add_argument("--extras", action="store_true", help="post-hoc controls only: usage-only path U and the endpoint-matched look-alike test")
    a = ap.parse_args(argv)
    MIN_HITTER_PITCHES = a.min_hitter_pitches
    t0 = time.time()
    say(f"Gate 0 run: league {a.league}, eval from {a.eval_start}, direct-test split {a.split}, hitter history {MIN_HITTER_PITCHES}+ pitches")
    rows, early, starters = load(a.league, a.end)
    say(f"loaded {len(rows)} pitches, {len(starters)} starter-games, {len(early)} with early-flight position ({time.time() - t0:.0f}s)")
    ok = lambda s: s.x_away is not None and s.z is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)
    swings = [s for s in rows if s.swing and ok(s)]
    takes = [s for s in rows if not s.swing]
    league = ContactModel([], swings, mode="shapecount")
    zone = CalledStrikeModel(takes)
    say(f"referee fit on {len(swings)} swings and {len(takes)} takes ({time.time() - t0:.0f}s)")
    P = [s for s in rows if (s.game_pk, s.pitcher) in starters and ok(s) and (s.game_pk, s.at_bat, s.pitch_no) in early]
    P.sort(key=lambda s: (s.date, s.game_pk, s.at_bat, s.pitch_no))
    say(f"{len(P)} starter pitches with complete data")
    loss, delta = [], []
    for i in range(0, len(P), 40000):
        l, d = referee(league, zone, P[i:i + 40000])
        loss.append(l)
        delta.append(d)
        say(f"  referee {min(i + 40000, len(P))}/{len(P)} ({time.time() - t0:.0f}s)")
    loss, delta = np.concatenate(loss), np.concatenate(delta)
    say(f"mean loss {loss.mean() * 100:.2f} runs per 100 pitches; share of pitches with any loss {(loss > 0).mean():.2f}")
    early_arr = np.array([early[(s.game_pk, s.at_bat, s.pitch_no)] for s in P])
    cells, ncell, isfb, fam, zr = build_cells(P)
    if a.raw:
        paths = ("L", "P", "E", "W", "U", "B1", "B3")
        sb = np.array([x.sz_bot or 1.5 for x in P])
        st = np.array([x.sz_top or 3.5 for x in P])
        zrr = (np.array([x.z for x in P]) - sb) / np.maximum(st - sb, 0.5)
        third = (zrr >= 1 / 3).astype(int) + (zrr >= 2 / 3).astype(int)
        strat = (fam * 3 + third) * 12 + np.array([min(x.balls, 3) * 3 + min(x.strikes, 2) for x in P])
        raw_out = {}
        acc, touches, nstart, hb = rolling(P, loss, delta, early_arr, cells, ncell, isfb, fam, a.eval_start, paths, raw_out=raw_out, strat=strat)
        say(f"{nstart} hitter-starts evaluated")
        report_raw(raw_out, touches, paths)
    elif a.excess:
        paths = ("L", "P", "E", "W")
        acc, touches, nstart, hb = rolling(P, loss, delta, early_arr, cells, ncell, isfb, fam, a.eval_start, paths)
        report_paths(acc, touches, nstart, paths, b2=False)
        report_excess(acc, touches, nstart, hb)
        report_excess_lift(acc)
    elif a.extras:
        say("POST-HOC CONTROLS (not pre-registered; run after the primary results were seen)")
        paths = PATHS + ("U", "N")
        acc, touches, nstart, hb = rolling(P, loss, delta, early_arr, cells, ncell, isfb, fam, a.eval_start, paths)
        report_paths(acc, touches, nstart, paths, b2=False)
        direct_test(P, early_arr, fam, zr, a.split, matched=True)
    else:
        acc, touches, nstart, hb = rolling(P, loss, delta, early_arr, cells, ncell, isfb, fam, a.eval_start)
        report_paths(acc, touches, nstart)
        reliability(P, loss, cells, ncell)
        direct_test(P, early_arr, fam, zr, a.split)
    say(f"\ntotal time {time.time() - t0:.0f}s")
    if a.out:
        pathlib.Path(a.out).write_text("\n".join(_OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
