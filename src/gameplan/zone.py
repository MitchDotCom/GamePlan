"""Called-strike surface fit from taken pitches, replacing the logistic stand-in in decision.py.

Location is put on the hitter's own zone: height as a fraction of (sz_bot .. sz_top), width in feet from
the middle of the plate, mirrored so + is away from the batter. Estimate is a Gaussian-kernel average of
strike (1) vs ball (0) over the nearest taken pitches, shrunk toward the stand-in curve where taken
pitches are sparse."""
from __future__ import annotations

from typing import Iterable

import numpy as np
from scipy.spatial import cKDTree

from .decision import p_called_strike
from .savant import SwingRow

BW = np.array([0.10, 0.07])       # feet across, fraction of zone height
DEFAULT_ZONE = (1.5, 3.5)


def _feat(x_away, z, sz_bot, sz_top):
    zn = (np.asarray(z, float) - sz_bot) / np.maximum(np.asarray(sz_top, float) - sz_bot, 0.5)
    return np.column_stack([np.asarray(x_away, float), zn]) / BW


class CalledStrikeModel:
    """Separate kernel surfaces for 0, 1 and 2 strikes (taken borderline pitches are called strikes far
    more often at 0 strikes than at 2, partly umpire behaviour and partly which pitches hitters take),
    plus a pooled surface used when the count is not given."""

    def __init__(self, takes: Iterable[SwingRow], k: int = 150, prior_m: float = 3.0, m_balls: float = 25.0):
        rows = [s for s in takes if not s.swing and s.take_call in ("strike", "ball") and s.x_away is not None]
        self.n = len(rows)
        self.m = prior_m
        self.k = k
        self.m_balls = m_balls     # pseudo-takes pulling a (balls, strikes) surface toward its strikes-only surface
        self.trees: dict = {}
        groups = {None: rows, 0: [s for s in rows if s.strikes == 0], 1: [s for s in rows if s.strikes == 1],
                  2: [s for s in rows if s.strikes >= 2]}
        for key, rs in groups.items():
            if not rs:
                continue
            sb = np.array([s.sz_bot if s.sz_bot else DEFAULT_ZONE[0] for s in rs])
            st = np.array([s.sz_top if s.sz_top else DEFAULT_ZONE[1] for s in rs])
            self.trees[key] = (cKDTree(_feat([s.x_away for s in rs], [s.z for s in rs], sb, st)),
                               np.array([s.take_call == "strike" for s in rs], float))
        for b in range(4):                      # one surface per full count, shrunk toward the strikes-only one
            for st_ in range(3):
                rs = [s for s in rows if min(s.balls, 3) == b and min(s.strikes, 2) == st_]
                if rs:
                    sb = np.array([s.sz_bot if s.sz_bot else DEFAULT_ZONE[0] for s in rs])
                    stp = np.array([s.sz_top if s.sz_top else DEFAULT_ZONE[1] for s in rs])
                    self.trees[(b, st_)] = (cKDTree(_feat([s.x_away for s in rs], [s.z for s in rs], sb, stp)),
                                            np.array([s.take_call == "strike" for s in rs], float))

    def _p_group(self, key, x, zz, sb, st, prior, m=None):
        if key not in self.trees:
            return prior
        m = self.m if m is None else m
        tree, y = self.trees[key]
        d, i = tree.query(_feat(x, zz, sb, st), k=min(self.k, len(y)), workers=-1)
        if d.ndim == 1:
            d, i = d[:, None], i[:, None]
        w = np.exp(-0.5 * d * d)
        return ((w * y[i]).sum(1) + m * prior) / (w.sum(1) + m)

    def p(self, x_away, z, sz_bot=DEFAULT_ZONE[0], sz_top=DEFAULT_ZONE[1], strikes=None, balls=None) -> np.ndarray:
        """Vectorised P(called strike | taken). strikes: None (pooled), an int, or an array. With balls
        also given, the full-count surface is used, shrunk toward the strikes-only surface."""
        x = np.atleast_1d(np.asarray(x_away, float))
        zz = np.atleast_1d(np.asarray(z, float))
        sb = np.broadcast_to(np.asarray(sz_bot, float), x.shape)
        st = np.broadcast_to(np.asarray(sz_top, float), x.shape)
        prior = np.array([p_called_strike(a, b, c, d) for a, b, c, d in zip(x, zz, sb, st)])
        if strikes is None:
            return self._p_group(None, x, zz, sb, st, prior)
        sk = np.minimum(np.broadcast_to(np.asarray(strikes, int), x.shape), 2)
        out = np.empty(len(x))
        for g in (0, 1, 2):
            m = sk == g
            if m.any():
                out[m] = self._p_group(g, x[m], zz[m], sb[m], st[m], prior[m])
        if balls is None:
            return out
        bl = np.minimum(np.broadcast_to(np.asarray(balls, int), x.shape), 3)
        res = out.copy()
        for b in range(4):
            for g in (0, 1, 2):
                m = (bl == b) & (sk == g)
                if m.any():
                    res[m] = self._p_group((b, g), x[m], zz[m], sb[m], st[m], out[m], self.m_balls)
        return res

    def __call__(self, x_away: float, z: float, sz_bot: float = DEFAULT_ZONE[0], sz_top: float = DEFAULT_ZONE[1],
                 strikes=None, balls=None) -> float:
        return float(self.p(x_away, z, sz_bot, sz_top, strikes, balls)[0])
