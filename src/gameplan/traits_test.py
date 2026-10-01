"""Pre-registered test: does a hitter's own swing path move the go / no-go call?  (the core thesis)

Question. A hitter's expected bat speed, swing length and attack angle for a given pitch and count (swing_traits.py: league
least squares plus a shrunk personal deviation, fit only on swings before the cutoff) are known before the pitch is thrown. Do
they predict held-out swing outcomes beyond what the current hitter model (ContactModel, shape plus count, with its hitter term)
already predicts?

Held out: swings on or after the cutoff against starters (2025: 2025-07-01). Models and traits are fit on swings before it.

Outcomes and baselines (no outcome of the swing being scored enters any feature):
  whiff      P(whiff | swing). Baseline: the hitter model's whiff probability. Stacked: logit(baseline) + theta . features.
  damage     xwOBA on contact, balls in play only. Baseline: the hitter model's xwOBA on contact. Stacked: baseline + theta . features.
Features (his deviation from the league expectation for the same pitch and count, so the baseline is not repeated):
  d_aa, d_aa x (league VBA - 17)/10   attack angle; the second term is the first-order effect under the league whiff curve,
                                      which is lowest near a 17 degree bat-ball angle (docs/plane_match.txt)
  d_bs, d_sl                          bat speed, swing length
  z_pers                              personal sweet band: his own whiff-versus-VBA curve (ridge toward the league curve, lambda in
                                      swings) applied to his expected VBA, minus the league curve
Feature blocks are scored alone and together: PATH (d_aa terms), SPEED (d_bs, d_sl), PERSONAL (z_pers), ALL.

Scoring. Theta is fit on other hitters only (10-fold, folds by hitter), so a hitter's own held-out swings never fit his
coefficients. Reported: out-of-fold improvement per swing (log-loss for whiff, mean squared error for damage) with a 95% interval
from a hitter-cluster bootstrap (2000 draws).

GATE, fixed before the first run. The thesis passes for an outcome if ALL is better than baseline with the interval above zero
on the 2025 test AND the sign repeats on the 2024 confirmation (2024 has bat speed and swing length; attack-angle blocks are
scored only where the field exists). A block that is better in the interval earns its place in the plan; a block whose interval
includes zero stays a descriptive panel. Nothing is adopted automatically.

    python -m gameplan.traits_test --b25 data/b3 --pitchers data/p2 --cutoff 2025-07-01 --b24 data/b24 --cutoff24 2024-07-01
"""
from __future__ import annotations

import argparse

import numpy as np

from .shape import ContactModel, raw_swing
from .swing_traits import HitterTraits, LeagueTraits, _design
from .validate_mlb import load_batters, load_start_keys

VBA_CENTER = 17.0
LAMBDA_PERSONAL = 150.0      # CHOICE: swings of pull toward the league whiff-versus-VBA curve
MIN_TRAIN = 300
BOOT = 2000
FEATURES = ("d_aa", "d_aa_x", "d_bs", "d_sl", "z_pers")
BLOCKS = {"PATH": (0, 1), "SPEED": (2, 3), "PERSONAL": (4,), "ALL": (0, 1, 2, 3, 4)}


def _fit_logit(F, y, off, lam=1.0, iters=30, prior=None):
    k = F.shape[1]
    prior = np.zeros(k) if prior is None else prior
    w = prior.copy()
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(off + F @ w, -30, 30)))
        g = F.T @ (p - y) + lam * (w - prior)
        H = (F * (p * (1 - p))[:, None]).T @ F + lam * np.eye(k)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w


def _vba_feats(aa, vaa):
    x = (np.asarray(aa, float) - np.asarray(vaa, float) - VBA_CENTER) / 10.0
    return np.column_stack([np.ones_like(x), x, x ** 2])


def build_rows(batters, cutoff, start_keys=None, min_train=MIN_TRAIN):
    """One record per held-out swing with a complete context, grouped by hitter."""
    league_train = [s for r in batters.values() for s in r if s.swing and s.date < cutoff]
    league = ContactModel([], league_train, mode="shapecount")
    lt = LeagueTraits(league_train)
    ltr = [s for s in league_train if s.attack_angle is not None and s.vaa is not None]
    beta_lg = _fit_logit(_vba_feats([s.attack_angle for s in ltr], [s.vaa for s in ltr]), np.array([s.whiff for s in ltr], float),
                         np.zeros(len(ltr)), lam=1.0) if len(ltr) > 1000 else None
    out = []
    for h, rs in batters.items():
        train = [s for s in rs if s.swing and s.date < cutoff]
        test = [s for s in rs if s.swing and s.date >= cutoff and s.x_away is not None
                and None not in (s.velo, s.ivb, s.hb, s.vaa) and (start_keys is None or (s.game_pk, s.at_bat, s.pitch_no) in start_keys)]
        if len(train) < min_train or not test:
            continue
        m = ContactModel.for_hitter(train, league)
        Q = np.array([raw_swing(s, "shapecount") for s in test], float)
        _, hit = m.predict_pair(Q)
        ht = HitterTraits.fit(train, lt)
        X, _, keep = _design(test)
        if not keep:
            continue
        exp, _ = ht.expected_for(test)
        d = {}
        for t in ("attack_angle", "bat_speed", "swing_length"):
            d[t] = (exp[t] - lt.predict(X, t)) if t in exp else np.zeros(len(keep))
        vaa = np.array([test[k].vaa for k in keep])
        lg_aa = lt.predict(X, "attack_angle") if "attack_angle" in lt.coef else np.full(len(keep), VBA_CENTER)
        vba_lg = lg_aa - vaa
        z_pers = np.zeros(len(keep))
        mine = [s for s in train if s.attack_angle is not None and s.vaa is not None]
        if beta_lg is not None and "attack_angle" in exp and len(mine) >= 100:
            bh = _fit_logit(_vba_feats([s.attack_angle for s in mine], [s.vaa for s in mine]), np.array([s.whiff for s in mine], float),
                            np.zeros(len(mine)), lam=LAMBDA_PERSONAL, prior=beta_lg)
            Fe = _vba_feats(exp["attack_angle"], vaa)
            Fl = _vba_feats(lg_aa, vaa)
            z_pers = (Fe @ bh - Fl @ beta_lg)
        F = np.column_stack([d["attack_angle"], d["attack_angle"] * (vba_lg - VBA_CENTER) / 10.0, d["bat_speed"], d["swing_length"], z_pers])
        sel = np.array(keep)
        out.append({"hitter": h, "F": F, "whiff": np.array([test[k].whiff for k in keep], float),
                    "p_whiff": np.clip(hit["whiff"][sel], 1e-4, 1 - 1e-4),
                    "xw": np.array([test[k].xwoba if test[k].xwoba is not None else np.nan for k in keep], float),
                    "p_xw": hit["xw"][sel]})
    return out


def _folds(n_h, k=10, seed=11):
    rng = np.random.default_rng(seed)
    return rng.permutation(n_h) % k


def _score(rows, cols, outcome, k=10):
    """Out-of-fold per-hitter (sum improvement, count) for one outcome, using feature columns `cols`."""
    fold = _folds(len(rows), k)
    per = np.zeros((len(rows), 2))
    for f in range(k):
        tr = [r for r, g in zip(rows, fold) if g != f]
        te = [(i, r) for i, (r, g) in enumerate(zip(rows, fold)) if g == f]
        Ftr = np.concatenate([r["F"][:, cols] for r in tr])
        mu, sd = Ftr.mean(0), Ftr.std(0) + 1e-9
        if outcome == "whiff":
            y = np.concatenate([r["whiff"] for r in tr])
            off = np.concatenate([np.log(r["p_whiff"] / (1 - r["p_whiff"])) for r in tr])
            w = _fit_logit((Ftr - mu) / sd, y, off, lam=1.0)
        else:
            ok = [~np.isnan(r["xw"]) for r in tr]
            y = np.concatenate([r["xw"][o] - r["p_xw"][o] for r, o in zip(tr, ok)])
            Fb = ((Ftr - mu) / sd)[np.concatenate(ok)]
            w = np.linalg.solve(Fb.T @ Fb + 1.0 * np.eye(len(cols)), Fb.T @ y)
        for i, r in te:
            Fz = (r["F"][:, cols] - mu) / sd
            if outcome == "whiff":
                lo = np.log(r["p_whiff"] / (1 - r["p_whiff"]))
                p1 = 1 / (1 + np.exp(-(lo + Fz @ w)))
                p0 = r["p_whiff"]
                ll = lambda p: -(r["whiff"] * np.log(np.clip(p, 1e-6, 1)) + (1 - r["whiff"]) * np.log(np.clip(1 - p, 1e-6, 1)))
                per[i] = ((ll(p0) - ll(p1)).sum(), len(p0))
            else:
                ok = ~np.isnan(r["xw"])
                if not ok.any():
                    continue
                e0 = (r["xw"][ok] - r["p_xw"][ok]) ** 2
                e1 = (r["xw"][ok] - (r["p_xw"][ok] + Fz[ok] @ w)) ** 2
                per[i] = ((e0 - e1).sum(), ok.sum())
    return per


def _interval(per, seed=3):
    rng = np.random.default_rng(seed)
    n = len(per)
    draws = []
    for _ in range(BOOT):
        idx = rng.integers(0, n, n)
        s = per[idx]
        draws.append(s[:, 0].sum() / max(s[:, 1].sum(), 1))
    est = per[:, 0].sum() / max(per[:, 1].sum(), 1)
    return est, np.percentile(draws, 2.5), np.percentile(draws, 97.5)


def report(rows, label, blocks=BLOCKS):
    n_sw = sum(len(r["whiff"]) for r in rows)
    print(f"\n== {label}: {len(rows)} hitters, {n_sw} held-out swings, {int(sum((~np.isnan(r['xw'])).sum() for r in rows))} balls in play")
    print(f"   {'block':<10}{'whiff: log-loss gain per swing (95% CI)':<48}{'damage: squared-error gain per BIP (95% CI)'}")
    res = {}
    for name, cols in blocks.items():
        cols = list(cols)
        w = _interval(_score(rows, cols, "whiff"))
        d = _interval(_score(rows, cols, "damage"))
        res[name] = (w, d)
        mark = lambda t: "PASS" if t[1] > 0 else "no"
        print(f"   {name:<10}{w[0]:+.5f} [{w[1]:+.5f}, {w[2]:+.5f}] {mark(w):<6}  {d[0]:+.6f} [{d[1]:+.6f}, {d[2]:+.6f}] {mark(d)}")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    ap.add_argument("--b24", default=None)
    ap.add_argument("--cutoff24", default="2024-07-01")
    a = ap.parse_args(argv)
    rows = build_rows(load_batters(a.b25), a.cutoff, load_start_keys(a.pitchers))
    report(rows, f"2025 test (swings vs starters from {a.cutoff})")
    if a.b24:
        rows24 = build_rows(load_batters(a.b24), a.cutoff24, None)
        report(rows24, f"2024 confirmation (all pitchers, from {a.cutoff24}; blocks need the fields that exist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
