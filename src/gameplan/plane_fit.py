"""Plane fit with controls (plan WS2): does the bat-ball angle still predict whiffs once pitch, location, count and the hitter are held fixed?

The raw league table (plane_match.py) shows whiffs lowest near a 15 to 18 degree vertical bat-ball angle (VBA = attack angle minus the
pitch's vertical approach angle). That table does not control for what kind of pitch it was, where it was, the count, or who swung, and
the realized angle is partly the hitter's reaction to the pitch. So three logistic models of P(whiff | swing) are scored out of sample:

  M0  controls: pitch family, velocity, height in the zone (and square), distance from the plate center line (away/in, and square),
      strike and ball count, the pitch's own approach angle (and square), induced vertical and horizontal break, plus a shrunk hitter
      intercept (fit on training swings only). The approach angle is a control on purpose: VBA contains it, so without it the angle
      block could win on pitch shape alone and not on how the bat path fits the pitch.
  M1  M0 + a piecewise-linear VBA curve using the REALIZED angle. Shows the shape of the curve with controls. Not gated: the realized
      angle is partly an outcome of the swing.
  M2  M0 + the same curve using his EXPECTED angle, known before the pitch (swing_traits: league least squares plus his shrunk
      deviation, fit on training swings only). This is the planned angle, and it is what a plan could use.

GATE, fixed before the first run. The plane-fit verdict (good / poor fit label) ships only if M2 beats M0 on held-out whiffs with the
95% hitter-cluster bootstrap interval above zero on 2025 AND on the 2024 confirmation. Otherwise the plane view shows the curve with
sample sizes and no verdict. Contact quality is not scored here (damage tests are WS1).

Train before the cutoff, test on or after it, all pitchers. Test hitters without training swings get a zero intercept.

    python -m gameplan.plane_fit --league data/league --cutoff 2025-07-01 --b24 data/b24 --cutoff24 2024-07-01"""
from __future__ import annotations

import argparse
import glob
import pathlib
from collections import defaultdict

import numpy as np

from .savant import parse_swings
from .swing_traits import HitterTraits, LeagueTraits, _design

FAMILY = {"FF": 1, "SI": 1, "FC": 1, "SL": 2, "ST": 2, "SV": 2, "CU": 2, "KC": 2, "CS": 2, "CH": 3, "FS": 3, "FO": 3}
KNOTS = (0.0, 6.0, 12.0, 18.0, 24.0, 30.0, 36.0)
LAM_H = 20.0
BOOT = 2000
SEED = 11
BINS = np.arange(-12.0, 45.0, 6.0)


def load(folder: str):
    rows = []
    for f in sorted(glob.glob(str(pathlib.Path(folder) / "*.csv"))):
        for s in parse_swings(open(f, encoding="utf-8-sig").read()):
            if (s.attack_angle is not None and s.vaa is not None and s.bat_speed is not None and s.pitch_type in FAMILY
                    and s.ivb is not None and s.hb is not None):
                rows.append(s)
    return rows


def controls(s):
    zr = ((s.z - (s.sz_bot or 1.5)) / max((s.sz_top or 3.5) - (s.sz_bot or 1.5), 0.5)) - 0.5
    f = FAMILY[s.pitch_type]
    return [1.0, f == 2, f == 3, (s.velo - 90.0) / 5.0, zr, zr * zr, s.x_away, s.x_away ** 2,
            float(s.strikes == 1), float(s.strikes >= 2), float(s.balls >= 2),
            s.vaa + 6.0, (s.vaa + 6.0) ** 2 / 4.0, (s.ivb - 12.0) / 8.0, s.hb / 8.0]


def hinge(v):
    v = np.asarray(v, float)
    cols = [v] + [np.maximum(v - k, 0.0) for k in KNOTS]
    return np.stack(cols, axis=1)


def _sigmoid(t):
    return 1.0 / (1.0 + np.exp(-np.clip(t, -30, 30)))


def fit_logit(X, y, hit_idx, n_h, iters=4):
    """Logistic regression with a ridge-shrunk intercept per hitter (backfitting). Returns (beta, hitter offsets)."""
    p = X.shape[1]
    beta = np.zeros(p)
    off = np.zeros(n_h)
    pen = np.eye(p) * 1e-3
    pen[0, 0] = 0.0
    for _ in range(iters):
        for _ in range(3):
            eta = X @ beta + off[hit_idx]
            mu = _sigmoid(eta)
            w = np.maximum(mu * (1 - mu), 1e-6)
            z = eta - off[hit_idx] + (y - mu) / w
            A = X.T @ (X * w[:, None]) + pen
            beta = np.linalg.solve(A, X.T @ (w * z))
        eta = X @ beta + off[hit_idx]
        mu = _sigmoid(eta)
        w = np.maximum(mu * (1 - mu), 1e-6)
        g = np.bincount(hit_idx, weights=y - mu, minlength=n_h)
        h = np.bincount(hit_idx, weights=w, minlength=n_h)
        off = off + g / (h + LAM_H)
    return beta, off


def _logloss(y, mu):
    mu = np.clip(mu, 1e-6, 1 - 1e-6)
    return -(y * np.log(mu) + (1 - y) * np.log(1 - mu))


def _boot(batters, diff):
    hs = {}
    for b, d in zip(batters, diff):
        t = hs.setdefault(b, [0.0, 0])
        t[0] += d
        t[1] += 1
    sums = np.array([v[0] for v in hs.values()])
    ns = np.array([v[1] for v in hs.values()])
    rng = np.random.default_rng(SEED)
    out = []
    for _ in range(BOOT):
        i = rng.integers(0, len(sums), len(sums))
        out.append(sums[i].sum() / ns[i].sum())
    return float(sums.sum() / ns.sum()), float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def run(swings, cutoff, label):
    tr = [s for s in swings if s.date < cutoff]
    te = [s for s in swings if s.date >= cutoff]
    lg = LeagueTraits(tr)
    ht = defaultdict(list)
    for s in tr:
        ht[s.batter].append(s)
    hid = {b: i for i, b in enumerate(sorted(ht))}
    hts = {b: HitterTraits.fit(v, lg) for b, v in ht.items()}

    def prep(rows, train):
        X, y, bat, vba_r, vba_e, hi = [], [], [], [], [], []
        by = defaultdict(list)
        for k, s in enumerate(rows):
            by[s.batter].append(k)
        keep = {}
        for b, ks in by.items():
            m = hts.get(b)
            sub = [rows[k] for k in ks]
            if m is None:
                m = HitterTraits(lg)
            ex, kk = m.expected_for(sub)
            if "attack_angle" not in ex:
                continue
            for pos, j in enumerate(kk):
                keep[ks[j]] = float(ex["attack_angle"][pos])
        for k, s in enumerate(rows):
            if k not in keep or s.x_away is None or s.velo is None or s.z is None:
                continue
            X.append(controls(s))
            y.append(float(s.whiff))
            bat.append(s.batter)
            vba_r.append(s.attack_angle - s.vaa)
            vba_e.append(keep[k] - s.vaa)
            hi.append(hid.get(s.batter, -1))
        return np.array(X, float), np.array(y), bat, np.array(vba_r), np.array(vba_e), np.array(hi)

    Xtr, ytr, btr, rtr, etr, htr = prep(tr, True)
    Xte, yte, bte, rte, ete, hte = prep(te, False)
    m = htr >= 0
    Xtr, ytr, rtr, etr, htr = Xtr[m], ytr[m], rtr[m], etr[m], htr[m]
    n_h = len(hid)

    def score(extra_tr, extra_te):
        A = Xtr if extra_tr is None else np.hstack([Xtr, extra_tr])
        B = Xte if extra_te is None else np.hstack([Xte, extra_te])
        beta, off = fit_logit(A, ytr, htr, n_h)
        o = np.where(hte >= 0, off[np.maximum(hte, 0)], 0.0)
        return _sigmoid(B @ beta + o), beta, off

    mu0, _, _ = score(None, None)
    mu1, b1, off1 = score(hinge(rtr), hinge(rte))
    mu2, _, _ = score(hinge(etr), hinge(ete))
    l0 = _logloss(yte, mu0)
    print(f"== {label}: train {len(ytr)} swings, test {len(yte)} swings, {len(set(bte))} test hitters; baseline M0 whiff log-loss {l0.mean():.4f}")
    res = {}
    for name, mu in (("M1 realized angle (shape, not gated)", mu1), ("M2 expected angle (GATED)", mu2)):
        g, lo, hi_ = _boot(bte, l0 - _logloss(yte, mu))
        res[name] = (g, lo, hi_)
        print(f"   {name:40s} gain per swing {g:+.5f} [{lo:+.5f}, {hi_:+.5f}]  {'PASS' if lo > 0 else 'no'}")
    # controlled shape: predicted whiff with the realized angle set to a bin center, everything else as observed (test swings)
    print("   VBA     raw whiff (test)   controlled whiff (M1, angle set)   swings")
    for c in BINS + 3.0:
        raw = (rte >= c - 3) & (rte < c + 3)
        if raw.sum() < 200:
            continue
        o = np.where(hte >= 0, off1[np.maximum(hte, 0)], 0.0)
        pd = _sigmoid(np.hstack([Xte, hinge(np.full(len(rte), c))]) @ b1 + o).mean()
        print(f"   {c - 3:4.0f}-{c + 3:<3.0f} {yte[raw].mean():10.3f} {pd:22.3f} {int(raw.sum()):15d}")
    return res["M2 expected angle (GATED)"][1] > 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    ap.add_argument("--b24")
    ap.add_argument("--cutoff24", default="2024-07-01")
    a = ap.parse_args(argv)
    ok25 = run(load(a.league), a.cutoff, "2025 test")
    ok24 = run(load(a.b24), a.cutoff24, "2024 confirmation") if a.b24 else None
    print(f"\nVerdict label ships: {'YES' if ok25 and ok24 else 'NO'} (2025 {ok25}, 2024 {ok24})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
