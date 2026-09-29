"""Inference helpers that fix two audit holes: intervals that resampled hitters only, and no
multiplicity correction.

Two-way (pigeonhole) cluster bootstrap: resample hitters and pitchers independently with replacement;
an observation's weight is (times its hitter was drawn) x (times its pitcher was drawn). This captures
that pitches share both a hitter and a pitcher. It is approximate and, if anything, conservative, which
is the right direction here.

Multiplicity: Holm (controls the chance of any false positive) and Benjamini-Hochberg (controls the
false-discovery rate) over a stated family of headline tests."""
from __future__ import annotations

from typing import Callable

import numpy as np


def two_way_draws(h_idx: np.ndarray, p_idx: np.ndarray, stat: Callable[[np.ndarray], float],
                  n: int = 300, seed: int = 0) -> tuple[float, np.ndarray]:
    """Point estimate (unit weights) and bootstrap draws of stat(weights)."""
    rng = np.random.default_rng(seed)
    nh, npi = int(h_idx.max()) + 1, int(p_idx.max()) + 1
    point = stat(np.ones(len(h_idx)))
    draws = np.empty(n)
    for k in range(n):
        ch = np.bincount(rng.integers(0, nh, nh), minlength=nh)
        cp = np.bincount(rng.integers(0, npi, npi), minlength=npi)
        draws[k] = stat((ch[h_idx] * cp[p_idx]).astype(float))
    return point, draws


def interval(point: float, draws: np.ndarray, level: float = 0.95) -> tuple[float, float, float]:
    lo, hi = np.percentile(draws[~np.isnan(draws)], [50 * (1 - level), 100 - 50 * (1 - level)])
    return point, float(lo), float(hi)


def two_sided_p(draws: np.ndarray, null: float = 0.0) -> float:
    """Percentile-bootstrap two-sided p-value against `null`; resolution is 1 / len(draws)."""
    d = draws[~np.isnan(draws)]
    p = 2 * min((d <= null).mean(), (d >= null).mean())
    return float(min(max(p, 1.0 / (len(d) + 1)), 1.0))


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min((m - i) * p, 1.0))
        out[k] = run
    return out


def benjamini_hochberg(pvals: dict[str, float]) -> dict[str, float]:
    """BH adjusted p-values (q-values)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1], reverse=True)
    m, out, run = len(items), {}, 1.0
    for i, (k, p) in enumerate(items):
        run = min(run, p * m / (m - i))
        out[k] = min(run, 1.0)
    return out


def report_family(name_to_p: dict[str, float]) -> str:
    h, b = holm(name_to_p), benjamini_hochberg(name_to_p)
    lines = [f"  {'test':<44} {'raw p':>8} {'Holm':>8} {'BH':>8}"]
    for k, p in sorted(name_to_p.items(), key=lambda kv: kv[1]):
        lines.append(f"  {k:<44} {p:>8.4f} {h[k]:>8.4f} {b[k]:>8.4f}")
    return "\n".join(lines)
