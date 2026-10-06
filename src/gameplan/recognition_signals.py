"""Gate 0b (docs/GATE0B_PREREGISTRATION.md): is pitch-type blindness a measurable hitter skill, and do extension and ride matter beyond the radar gun?

    python -m gameplan.recognition_signals --league data/league --split 2025-07-01 --out docs/gate0b_results_2025.txt"""
from __future__ import annotations

import argparse
import csv
import glob
import pathlib
import time
from collections import defaultdict

import numpy as np

from . import recognition_paths as rp
from .plane_fit import _boot, _logloss, _sigmoid, fit_logit
from .shape import ContactModel
from .traits_test import _fit_logit as ridge_logit
from .zone import CalledStrikeModel

say = rp.say
BOOT = 1000
K_DEV = 100.0


def load_ext(league_dir, end=None):
    ext = {}
    for f in sorted(glob.glob(str(pathlib.Path(league_dir) / "*.csv"))):
        if end and pathlib.Path(f).stem > end:
            break
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            try:
                ext[(r["game_pk"], int(float(r["at_bat_number"])), int(float(r["pitch_number"])))] = float(r["release_extension"])
            except (KeyError, ValueError):
                pass
    return ext


def sb(r):
    return 2 * r / (1 + r) if r > -1 else float("nan")


def boot_corr(x, y, extra=None, seed=5):
    rng = np.random.default_rng(seed)
    def stat(i):
        a, b = x[i], y[i]
        if extra is not None:
            e = extra[i]
            A = np.column_stack([np.ones(len(e)), e])
            a = a - A @ np.linalg.lstsq(A, a, rcond=None)[0]
            b = b - A @ np.linalg.lstsq(A, b, rcond=None)[0]
        return np.corrcoef(a, b)[0, 1]
    est = stat(np.arange(len(x)))
    bs = [stat(rng.integers(0, len(x), len(x))) for _ in range(BOOT)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return est, lo, hi


def test1(bat, date, game, swing, loss, delta, xa, zr, strikes, split):
    say("\nTEST 1: pitch-type blindness (g = his raw slope of swinging on the type signal; higher = uses it more; amended 2026-10-06, see the pre-registration)")
    bx = np.clip(((xa + 3) / 0.3).astype(int), 0, 19)
    bz = np.clip(((zr + 1) / 0.2).astype(int), 0, 14)
    cell = (bx * 15 + bz) * 3 + np.minimum(strikes, 2)
    nc = 20 * 15 * 3
    n = np.bincount(cell, minlength=nc)
    md = np.bincount(cell, weights=delta, minlength=nc) / np.maximum(n, 1)
    ms = np.bincount(cell, weights=swing, minlength=nc) / np.maximum(n, 1)
    keep = (n[cell] >= 30).astype(float)
    t, s = delta - md[cell], swing - ms[cell]
    bL = (s * t * keep).sum() / (t * t * keep).sum()
    ids, inv = np.unique(bat, return_inverse=True)
    H = len(ids)
    order = np.lexsort((game, date))
    par = np.zeros(len(bat), int)
    seen = defaultdict(dict)
    for i in order:
        g = seen[inv[i]]
        if game[i] not in g:
            g[game[i]] = len(g)
        par[i] = g[game[i]] % 2
    def slopes(mask):
        w = keep * mask
        cnt = np.bincount(inv, weights=w, minlength=H)
        return np.bincount(inv, weights=s * t * w, minlength=H) / np.maximum(np.bincount(inv, weights=t * t * w, minlength=H), 1e-9), cnt
    g_all, c_all = slopes(np.ones(len(bat)))
    g_odd, c_odd = slopes((par == 0).astype(float))
    g_even, c_even = slopes((par == 1).astype(float))
    ok = (c_odd >= 150) & (c_even >= 150)
    r = np.corrcoef(g_odd[ok], g_even[ok])[0, 1]
    say(f"league slope {bL:.3f} (negative = hitters swing less when the type signal favors swinging); hitters with 300+ pitches {(c_all >= 300).sum()}; g spread (10th, 50th, 90th pct) {np.percentile(g_all[c_all >= 300], [10, 50, 90]).round(2)}")
    say(f"reliability: odd vs even games r {r:+.3f} over {ok.sum()} hitters, corrected {sb(r):+.3f}  {'PASS' if sb(r) >= 0.4 else 'no'}")
    hi = np.abs(t) >= np.quantile(np.abs(t[keep > 0]), 0.70)
    first, second = date < split, date >= split
    g1, c1 = slopes(first.astype(float))
    def rate(mask):
        w = (hi & mask).astype(float)
        return np.bincount(inv, weights=loss * w, minlength=H) / np.maximum(np.bincount(inv, weights=w, minlength=H), 1), np.bincount(inv, weights=w, minlength=H)
    r1, n1 = rate(first)
    r2, n2 = rate(second)
    ok2 = (c1 >= 150) & (n1 >= 50) & (n2 >= 50)
    est, lo, hi_ = boot_corr(g1[ok2], r2[ok2])
    pest, plo, phi = boot_corr(g1[ok2], r2[ok2], extra=r1[ok2])
    say(f"predicts mistakes ({ok2.sum()} hitters): first-half g vs second-half loss on high-type-signal pitches: r {est:+.3f} [{lo:+.3f}, {hi_:+.3f}]; "
        f"after removing his first-half loss on the same pitches: {pest:+.3f} [{plo:+.3f}, {phi:+.3f}]  {'PASS' if (hi_ < 0 and phi < 0) else 'no'}")
    ooz = ((np.abs(xa) > 0.83) | (zr < 0) | (zr > 1)).astype(float)
    sw = np.bincount(inv, weights=swing * ooz, minlength=H) / np.maximum(np.bincount(inv, weights=ooz, minlength=H), 1)
    okz = c_all >= 300
    rz = np.corrcoef(g_all[okz], sw[okz])[0, 1]
    say(f"separate from zone control: correlation of g with his out-of-zone swing rate {rz:+.3f}  ({'separate skills' if abs(rz) < 0.5 else 'overlapping'})")


def test2(bat, date, game, swing, whiff, xa, zr, velo, ivb, hb, vaa, strikes, balls, fam, ext, pit, split):
    say("\nTEST 2: extension-adjusted velocity and hitter-specific sensitivities (whiff per swing)")
    D = 60.5 - ext - 17.0 / 12.0
    adj = velo * np.nanmean(D) / D
    tr_all = date < split
    sel = (swing == 1) & ~np.isnan(adj)
    ids, inv = np.unique(bat, return_inverse=True)
    pids = {p: j for j, p in enumerate(sorted(set(pit)))}
    gi = np.array([pids[p] for p in pit])
    def design(mask):
        mu = lambda a: (a[mask & tr_all].mean(), a[mask & tr_all].std() + 1e-9)
        z = lambda a: (a - mu(a)[0]) / mu(a)[1]
        X0 = np.column_stack([np.ones(len(xa)), fam == 1, fam == 2, xa, xa ** 2, zr, zr ** 2, z(velo), z(ivb), z(hb), z(vaa),
                              (strikes == 1), (strikes == 2), (balls >= 2)]).astype(float)
        return X0, z
    for label, mask in (("all pitches", sel), ("fastballs only", sel & (fam == 0))):
        X0, z = design(mask)
        X1 = np.column_stack([X0, z(adj)])
        a, b = mask & tr_all, mask & ~tr_all
        res = {}
        for lab, X in (("base", X0), ("+adj velo", X1)):
            beta, off = fit_logit(X[a], whiff[a], gi[a], len(pids))
            res[lab] = (_logloss(whiff[b], _sigmoid(X[b] @ beta + off[gi[b]])), beta)
        gain, lo, hi = _boot(list(bat[b]), res["base"][0] - res["+adj velo"][0])
        say(f"{label}: {a.sum()} train, {b.sum()} test swings; extension-adjusted velocity log-loss gain {gain:+.5f} [{lo:+.5f}, {hi:+.5f}], coefficient {res['+adj velo'][1][-1]:+.3f} per sd  {'PASS' if lo > 0 else 'no'}")
    # hitter-specific sensitivities
    order = np.lexsort((game, date))
    par = np.zeros(len(bat), int)
    seen = defaultdict(dict)
    for i in order:
        g = seen[inv[i]]
        if game[i] not in g:
            g[game[i]] = len(g)
        par[i] = g[game[i]] % 2
    for name, feat, mask in (("fastball ride (vertical break)", ivb, sel & (fam == 0)), ("fastball extension-adjusted velocity", adj, sel & (fam == 0)),
                             ("breaking-ball run (horizontal break)", hb, sel & (fam == 1))):
        X0, z = design(mask)
        zf = z(feat)
        X1 = np.column_stack([X0, zf])
        a, b = mask & tr_all, mask & ~tr_all
        beta, off = fit_logit(X1[a], whiff[a], gi[a], len(pids))
        eta = X1 @ beta + off[gi]
        def dev(sub):
            w = np.zeros(len(ids))
            for h in range(len(ids)):
                m = sub & (inv == h)
                if m.sum() >= 40:
                    w[h] = ridge_logit(zf[m][:, None], whiff[m], eta[m], lam=K_DEV)[0]
            return w
        w_tr = dev(mask & tr_all)
        p0 = _sigmoid(eta[b])
        p1 = _sigmoid(eta[b] + w_tr[inv[b]] * zf[b])
        gain, lo, hi = _boot(list(bat[b]), _logloss(whiff[b], p0) - _logloss(whiff[b], p1))
        w_o, w_e = dev(mask & (par == 0)), dev(mask & (par == 1))
        okh = np.array([((mask & (par == 0) & (inv == h)).sum() >= 40) and ((mask & (par == 1) & (inv == h)).sum() >= 40) for h in range(len(ids))])
        r = np.corrcoef(w_o[okh], w_e[okh])[0, 1]
        say(f"{name}: hitter-specific slope (shrunk, K={K_DEV:.0f}); reliability odd vs even r {r:+.3f} over {okh.sum()} hitters, corrected {sb(r):+.3f} {'PASS' if sb(r) >= 0.4 else 'no'}; "
            f"second-half log-loss gain over the league slope {gain:+.5f} [{lo:+.5f}, {hi:+.5f}]  {'PASS' if lo > 0 else 'no'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    say(f"Gate 0b run: league {a.league}, split {a.split}")
    rows, early, starters = rp.load(a.league, a.end)
    ok = lambda s: s.x_away is not None and s.z is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)
    league = ContactModel([], [s for s in rows if s.swing and ok(s)], mode="shapecount")
    zone = CalledStrikeModel([s for s in rows if not s.swing])
    P = [s for s in rows if (s.game_pk, s.pitcher) in starters and ok(s) and (s.game_pk, s.at_bat, s.pitch_no) in early]
    P.sort(key=lambda s: (s.date, s.game_pk, s.at_bat, s.pitch_no))
    loss, delta = [], []
    for i in range(0, len(P), 40000):
        l, d = rp.referee(league, zone, P[i:i + 40000])
        loss.append(l)
        delta.append(d)
    loss, delta = np.concatenate(loss), np.concatenate(delta)
    ext_map = load_ext(a.league, a.end)
    say(f"{len(P)} starter pitches; extension for {sum((s.game_pk, s.at_bat, s.pitch_no) in ext_map for s in P)} ({time.time() - t0:.0f}s)")
    arr = lambda f, dt=float: np.array([f(s) for s in P], dt)
    bat, pit, date, game = arr(lambda s: s.batter, str), arr(lambda s: s.pitcher, str), arr(lambda s: s.date, str), arr(lambda s: s.game_pk, str)
    swing, whiff = arr(lambda s: s.swing), arr(lambda s: bool(s.whiff))
    xa, velo, ivb, hb, vaa = (arr(lambda s, k=k: getattr(s, k)) for k in ("x_away", "velo", "ivb", "hb", "vaa"))
    sb_, st_, z_ = arr(lambda s: s.sz_bot or 1.5), arr(lambda s: s.sz_top or 3.5), arr(lambda s: s.z)
    zr = (z_ - sb_) / np.maximum(st_ - sb_, 0.5)
    strikes, balls = arr(lambda s: s.strikes, int), arr(lambda s: s.balls, int)
    fam = arr(lambda s: rp.FAM_IDX.get(rp.FAMILY_OF.get(s.pitch_type, "OTH"), 3), int)
    ext = arr(lambda s: ext_map.get((s.game_pk, s.at_bat, s.pitch_no), np.nan))
    test1(bat, date, game, swing, loss, delta, xa, zr, strikes, a.split)
    test2(bat, date, game, swing, whiff, xa, zr, velo, ivb, hb, vaa, strikes, balls, fam, ext, pit, a.split)
    say(f"\ntotal time {time.time() - t0:.0f}s")
    if a.out:
        pathlib.Path(a.out).write_text("\n".join(rp._OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
