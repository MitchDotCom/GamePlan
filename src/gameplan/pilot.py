"""Pilot planning: what a real test of the plan can and cannot detect, and which process metrics are
reliable enough to use per hitter.

Outcome noise is large (per-pitch run value SD about 0.33 on swings, 0.08 on takes, from 2025 data), so
results-based tests need thousands of pitches per arm. Process metrics (decision value, chase rate, zone
swing rate, compliance) are far less noisy but only matter if they are stable per hitter and move with
the plan. This module gives the sample-size arithmetic, a stepped-rollout power simulation, and a
split-half reliability check on the process metrics.

    python -m gameplan.pilot --b25 data/league --pitchers data/league
"""
from __future__ import annotations

import argparse
import math

import numpy as np

from .constants import value as _const
from .decision import deltas_np

Z_ALPHA, Z_POWER = 1.96, 0.8416      # two-sided 5%, 80% power


def mde(n_per_arm: float, sd: float) -> float:
    """Smallest difference in means detectable with two equal arms (two-sample z approximation)."""
    return (Z_ALPHA + Z_POWER) * sd * math.sqrt(2.0 / n_per_arm)


def n_per_arm(effect: float, sd: float) -> float:
    return 2.0 * ((Z_ALPHA + Z_POWER) * sd / effect) ** 2


def stepped_power(n_hitters: int, n_periods: int, pitches_per_period: int, effect: float, sd_pitch: float,
                  sd_hitter: float = 0.0, sims: int = 400, seed: int = 0) -> float:
    """Power of a stepped rollout: hitters switch on the plan at staggered periods, all end on it.
    Analysis: hitter and period fixed effects, treatment coefficient, z-test. Aggregating pitches to
    hitter-period means, the noise SD of a mean is sd_pitch / sqrt(pitches_per_period)."""
    rng = np.random.default_rng(seed)
    start = np.linspace(1, n_periods - 1, n_hitters).round().astype(int)     # first treated period per hitter
    H, T = np.meshgrid(np.arange(n_hitters), np.arange(n_periods), indexing="ij")
    treat = (T >= start[:, None]).astype(float).ravel()
    h, t = H.ravel(), T.ravel()
    X = np.column_stack([treat, np.eye(n_hitters)[h], np.eye(n_periods)[t][:, 1:]])
    hits = 0
    for _ in range(sims):
        y = effect * treat + rng.normal(0, sd_hitter, n_hitters)[h] + rng.normal(0, sd_pitch / math.sqrt(pitches_per_period), len(h))
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        dof = len(y) - X.shape[1]
        cov = (resid @ resid / dof) * np.linalg.pinv(X.T @ X)
        hits += abs(beta[0] / math.sqrt(cov[0, 0])) > Z_ALPHA
    return hits / sims


def process_metric_reliability(frames, chase_pcs: float = 0.10, zone_pcs: float = 0.90) -> dict:
    """Split-half (alternate games) reliability across hitters for candidate pilot metrics.

    decision value per 100 pitches: expected runs from the actions taken vs the alternatives, by the model
    chase rate: swings / pitches with called-strike probability under chase_pcs
    zone swing rate: swings / pitches with called-strike probability over zone_pcs
    compliance: share of pitches with a strong count-aware call where the hitter did what the call said
    Returns {metric: (split-half r, Spearman-Brown full-length reliability, n hitters)}."""
    scale = _const("WOBA_SCALE_2025")
    per = {"decision value per 100 pitches": [], "chase rate": [], "zone swing rate": [], "compliance": []}
    for f in frames:
        d = deltas_np(f["p"]["whiff"], f["p"]["foul"], f["p"]["xw"], f["p_cs"], f["balls"], f["strikes"])
        games = np.unique(f["game"])
        if len(games) < 20:
            continue
        odd = np.isin(f["game"], games[::2])
        half = []
        for m in (odd, ~odd):
            sw = f["swing"][m]
            dv = np.where(sw, d[m], -d[m]) / scale
            pc = f["p_cs"][m]
            strong = np.abs(d[m]) >= 0.02
            follow = np.where(d[m] >= 0.02, sw, ~sw)[strong]
            half.append((100 * dv.mean(), sw[pc < chase_pcs].mean() if (pc < chase_pcs).sum() >= 20 else np.nan,
                         sw[pc > zone_pcs].mean() if (pc > zone_pcs).sum() >= 20 else np.nan,
                         follow.mean() if strong.sum() >= 20 else np.nan))
        for k, name in enumerate(per):
            per[name].append((half[0][k], half[1][k]))
    out = {}
    for name, pairs in per.items():
        a = np.array([p for p in pairs if not np.isnan(p).any()])
        if len(a) < 10:
            continue
        r = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
        out[name] = (r, 2 * r / (1 + r) if r > -1 else float("nan"), len(a))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", default=None, help="dir of per-day or per-player CSVs (needs the validate_mlb frames)")
    ap.add_argument("--pitchers", default=None)
    ap.add_argument("--cutoff", default="2025-07-01")
    a = ap.parse_args(argv)
    print("Sample size arithmetic (runs per pitch; SD from 2025: swings 0.33, takes 0.08, mixed about 0.21)")
    for n in (250, 600, 2500, 10000, 25000):
        print(f"  {n:>6} pitches per arm: minimum detectable difference {mde(n, 0.21):.4f} runs (mixed pitches), {mde(n, 0.33):.4f} (swings only)")
    print("Stepped rollout power (effect 0.005 runs/pitch on swings; 12 hitters, 8 periods, 400 swings per hitter-period):")
    print(f"  power {stepped_power(12, 8, 400, 0.005, 0.33, sd_hitter=0.02, sims=200):.2f}")
    if a.b25 and a.pitchers:
        from .validate_mlb import _frames, load_batters, load_start_keys
        from .zone import CalledStrikeModel
        b = load_batters(a.b25)
        zm = CalledStrikeModel([s for r in b.values() for s in r if not s.swing and s.date < a.cutoff])
        league_train = [s for r in b.values() for s in r if s.swing and s.date < a.cutoff]
        frames = _frames(b, a.cutoff, load_start_keys(a.pitchers), league_train, zm)
        print("\nSplit-half reliability of process metrics across hitters (alternate games):")
        for k, (r, sb, n) in process_metric_reliability(frames).items():
            print(f"  {k:<34} r={r:+.2f}  full-length reliability {sb:+.2f}  ({n} hitters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
