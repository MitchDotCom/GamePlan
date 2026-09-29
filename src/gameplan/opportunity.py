"""Where a starter throws, how often this hitter swings there, and what following the plan is worth.

plan_opportunity answers the question the earlier work never did: given the pitcher's actual location
distribution and the hitter's actual swing tendencies, how many runs per 100 pitches does the plan
offer if the hitter follows it? A GO cell he only swings at half the time leaves half of that cell's
swing-minus-take value on the table; a NO_GO cell he swings at often costs him."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.special import ndtr
from scipy.spatial import cKDTree

from .constants import value as _const
from .matchup import CELL_IN, X_RANGE, Z_RANGE, PlanSnapshot
from .plan import grid_centers
from .savant import SwingRow
from .shape import PitchRow, _type_code

LOC_SIGMA_FT = 0.20     # smoothing of a pitcher's location cloud (CHOICE; ~2.4 inches)


class LocationModel:
    """P(cell | pitch type) from a pitcher's own pitches, by cell mass of a Gaussian-smoothed cloud.
    Optionally conditioned on batter side and strike count, falling back to all pitches when a group has
    fewer than min_n pitches."""

    def __init__(self, pitches: Iterable[PitchRow], sigma: float = LOC_SIGMA_FT, min_n: int = 60):
        self.rows = [p for p in pitches if p.x_away is not None and p.z is not None]
        self.sigma, self.min_n = sigma, min_n
        step = CELL_IN / 12.0
        self.cells = grid_centers(X_RANGE, Z_RANGE, CELL_IN)
        self.step = step
        self.x0 = np.array([X_RANGE[0] + i * step for i, _, _, _ in self.cells])
        self.z0 = np.array([Z_RANGE[0] + j * step for _, j, _, _ in self.cells])

    def mass(self, pitch_type: str, stand: str | None = None, strikes: int | None = None) -> np.ndarray:
        rs = [p for p in self.rows if p.pitch_type == pitch_type]
        for keep in ((lambda p: p.stand == stand) if stand else None, (lambda p: p.strikes == strikes) if strikes is not None else None):
            if keep:
                sub = [p for p in rs if keep(p)]
                if len(sub) >= self.min_n:
                    rs = sub
        if not rs:
            return np.zeros(len(self.cells))
        px = np.array([p.x_away for p in rs])[:, None]
        pz = np.array([p.z for p in rs])[:, None]
        s = self.sigma
        mx = ndtr((self.x0 + self.step - px) / s) - ndtr((self.x0 - px) / s)
        mz = ndtr((self.z0 + self.step - pz) / s) - ndtr((self.z0 - pz) / s)
        return (mx * mz).mean(0)          # per-cell probability (mass off the grid is simply not counted)


class SwingRateModel:
    """P(swing | location, pitch type, strike count) for one hitter, shrunk to the league. Uses swings
    and takes (parse_swings(include_takes=True))."""

    K_SHRINK = 20.0

    def __init__(self, hitter_rows: Iterable[SwingRow], league_rows: Iterable[SwingRow]):
        def build(rows):
            rows = [s for s in rows if s.x_away is not None]
            X = np.array([(s.x_away / 0.25, s.z / 0.25, _type_code(s.pitch_type), min(s.strikes, 2) * 10.0) for s in rows], float)
            y = np.array([float(s.swing) for s in rows])
            return (cKDTree(X), y) if len(rows) else (None, y)
        self._h, self._l = build(list(hitter_rows)), build(list(league_rows))
        lg = list(league_rows)
        self._g = float(np.mean([s.swing for s in lg])) if lg else 0.45

    @staticmethod
    def _local(tree_y, Q, k):
        tree, y = tree_y
        if tree is None:
            return np.zeros(len(Q)), np.zeros(len(Q))
        d, i = tree.query(Q, k=min(k, len(y)), workers=-1)
        if d.ndim == 1:
            d, i = d[:, None], i[:, None]
        w = np.exp(-0.5 * d * d)
        return (w * y[i]).sum(1), w.sum(1)

    def p(self, x_away, z, pitch_type: str, strikes: int) -> np.ndarray:
        x = np.atleast_1d(np.asarray(x_away, float))
        zz = np.atleast_1d(np.asarray(z, float))
        Q = np.column_stack([x / 0.25, zz / 0.25, np.full(len(x), _type_code(pitch_type)),
                             np.full(len(x), min(strikes, 2) * 10.0)])
        ls, lw = self._local(self._l, Q, 300)
        prior = (ls + 3 * self._g) / (lw + 3)
        hs, hw = self._local(self._h, Q, 60)
        return (hs + self.K_SHRINK * prior) / (hw + self.K_SHRINK)


@dataclass(frozen=True)
class Opportunity:
    runs_per_100_pitches: float          # expected runs gained per 100 pitches if the hitter follows every called cell
    covered_share: float                 # share of pitches that land in a GO or NO_GO cell
    already_following: float             # share of covered pitches where his tendency already matches the call
    by_type: dict                        # pitch type -> runs per 100 pitches of that type
    top_cells: list                      # (key, runs_per_100_pitches) largest opportunities


def plan_opportunity(snap: PlanSnapshot, locations: LocationModel, swing_rate: SwingRateModel,
                     stand: str | None = None, scale: float | None = None, top: int = 8) -> Opportunity:
    scale = scale or _const("WOBA_SCALE_2025")
    sit = snap.situation
    cells = locations.cells
    gain = np.zeros(0)
    tot_gain = 0.0
    covered = follow_num = 0.0
    by_type, per_cell = {}, []
    xs = np.array([c[2] for c in cells])
    zs = np.array([c[3] for c in cells])
    for pt, a in snap.arsenal.items():
        m = locations.mass(pt, stand, min(sit.strikes, 2)) * a["usage"]
        psw = swing_rate.p(xs, zs, pt, sit.strikes)
        g_type = 0.0
        for n, (i, j, _, _) in enumerate(cells):
            c = snap.cells.get(f"{pt}|{i}|{j}")
            if not c or c["cls"] == "CONDITIONAL":
                continue
            d = c["delta"]
            g = (1 - psw[n]) * d if c["cls"] == "GO" else psw[n] * (-d)
            g_runs = m[n] * g / scale * 100
            g_type += g_runs
            per_cell.append((f"{pt}|{i}|{j}", g_runs))
            covered += m[n]
            follow_num += m[n] * (psw[n] if c["cls"] == "GO" else 1 - psw[n])
        by_type[pt] = g_type
        tot_gain += g_type
    per_cell.sort(key=lambda kv: -kv[1])
    return Opportunity(tot_gain, covered, follow_num / covered if covered else 0.0, by_type, per_cell[:top])
