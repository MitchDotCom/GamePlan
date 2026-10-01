"""Hitter swing traits from bat tracking, as low-dimensional relationships instead of heat-map cells.

A hitter's bat speed, swing length, attack angle and swing-path tilt change with the pitch (height, location,
speed) and with the count (hitters shorten up and slow down with strikes). Those relationships have a handful of
parameters, so a few hundred tracked swings pin them down far better than a grid of cells can (a median of 0.2 of a
hitter's own swings sits behind a plan cell).

Model, per trait y (standardized context x):
  league:   y = x . b_league                                  (least squares over all swings)
  hitter:   y - league prediction = x_h . d_h                  (ridge toward zero; lam in swings, so a hitter with n swings
                                                                keeps n / (n + lam) of his own deviation)
  expected swing for a pitch, before it is thrown or swung at:  league prediction + hitter deviation.

Nothing here uses the outcome of the swing being predicted. Whether the traits add predictive information beyond the
kernel model is a separate pre-registered test (traits_test.py); until it passes they are a descriptive panel."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np

from .savant import SwingRow

TRAITS = ("bat_speed", "swing_length", "attack_angle", "tilt")
LEAGUE_COLS = ("one", "zr", "zr2", "x", "velo", "ivb", "k1", "k2", "b2")
HITTER_COLS = ("one", "zr", "x", "k2", "velo")           # what a hitter's own deviation may depend on
LAMBDA = 60.0                                            # CHOICE until traits_test.py selects it on a validation block


def _zr(s: SwingRow) -> Optional[float]:
    if s.z is None:
        return None
    bot, top = s.sz_bot or 1.5, s.sz_top or 3.5
    return (s.z - bot) / max(top - bot, 0.5)


def context_row(s: SwingRow) -> Optional[np.ndarray]:
    """Standardizable context for the pitch and count. None when a needed field is missing."""
    zr = _zr(s)
    if zr is None or s.x_away is None or s.velo is None or s.ivb is None:
        return None
    return np.array([1.0, zr - 0.5, (zr - 0.5) ** 2, s.x_away, (s.velo - 90.0) / 5.0, (s.ivb - 12.0) / 8.0,
                     float(s.strikes == 1), float(s.strikes >= 2), float(s.balls >= 2)])


def _design(swings: Iterable[SwingRow], trait: Optional[str] = None):
    X, y, keep = [], [], []
    for k, s in enumerate(swings):
        c = context_row(s)
        if c is None:
            continue
        v = getattr(s, trait) if trait else 0.0
        if trait and v is None:
            continue
        X.append(c)
        y.append(v)
        keep.append(k)
    return np.array(X, float).reshape(-1, len(LEAGUE_COLS)), np.array(y, float), keep


class LeagueTraits:
    """Least-squares trait model over all swings (with a trait measurement and a complete context)."""

    def __init__(self, swings: Iterable[SwingRow]):
        swings = list(swings)
        self.coef, self.sd, self.n = {}, {}, {}
        for t in TRAITS:
            X, y, _ = _design(swings, t)
            if len(y) < 500:
                continue
            self.coef[t] = np.linalg.lstsq(X, y, rcond=None)[0]
            self.sd[t] = float(np.std(y - X @ self.coef[t]))
            self.n[t] = len(y)

    def predict(self, X: np.ndarray, trait: str) -> np.ndarray:
        return X @ self.coef[trait]


@dataclass
class HitterTraits:
    league: LeagueTraits
    dev: dict = field(default_factory=dict)         # trait -> deviation coefficients on HITTER_COLS
    n: dict = field(default_factory=dict)           # trait -> number of his swings with the trait
    lam: float = LAMBDA

    @classmethod
    def fit(cls, swings: Iterable[SwingRow], league: LeagueTraits, lam: float = LAMBDA) -> "HitterTraits":
        swings = list(swings)
        out = cls(league, lam=lam)
        idx = [LEAGUE_COLS.index(c) for c in HITTER_COLS]
        for t in league.coef:
            X, y, _ = _design(swings, t)
            if len(y) == 0:
                continue
            r = y - league.predict(X, t)
            H = X[:, idx]
            A = H.T @ H + lam * np.eye(len(idx))
            out.dev[t] = np.linalg.solve(A, H.T @ r)
            out.n[t] = len(y)
        return out

    def expected(self, X: np.ndarray, trait: str) -> np.ndarray:
        """League prediction plus his deviation, for each context row of X (LEAGUE_COLS order)."""
        base = self.league.predict(X, trait)
        if trait not in self.dev:
            return base
        return base + X[:, [LEAGUE_COLS.index(c) for c in HITTER_COLS]] @ self.dev[trait]

    def expected_for(self, swings: Iterable[SwingRow]):
        """({trait: expected values}, keep) for swings with a complete context; keep indexes the input order."""
        swings = list(swings)
        X, _, keep = _design(swings)
        return {t: self.expected(X, t) for t in self.league.coef}, keep

    def profile(self) -> dict:
        """Descriptive view: expected trait for a low, middle and high pitch and for zero versus two strikes, a typical
        fastball over the middle of the plate. Includes how much of his own deviation survives the shrinkage."""
        def ctx(zr, strikes):
            c = np.zeros(len(LEAGUE_COLS))
            c[[0, 1, 2, 3, 4, 5]] = [1.0, zr - 0.5, (zr - 0.5) ** 2, 0.0, 0.8, 0.5]
            c[LEAGUE_COLS.index("k2")] = float(strikes >= 2)
            c[LEAGUE_COLS.index("k1")] = float(strikes == 1)
            return c
        out = {}
        for t in self.league.coef:
            lo, mid, hi = (float(self.expected(ctx(z, 0)[None], t)[0]) for z in (0.15, 0.5, 0.85))
            two = float(self.expected(ctx(0.5, 2)[None], t)[0])
            lg_mid = float(self.league.predict(ctx(0.5, 0)[None], t)[0])
            out[t] = {"low": round(lo, 2), "mid": round(mid, 2), "high": round(hi, 2), "mid_two_strikes": round(two, 2),
                      "league_mid": round(lg_mid, 2), "n": self.n.get(t, 0),
                      "kept": round(self.n.get(t, 0) / (self.n.get(t, 0) + self.lam), 2)}
        return out
