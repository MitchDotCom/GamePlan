"""Shape-aware contact model and starter arsenals.

Hitter capability is estimated as a kernel-weighted local average over the hitter's own swings in
(location, pitch shape) space, shrunk toward a league prior built the same way. The pitcher side is
his arsenal (usage and average shape per pitch type) at a given time through the order.

Targets, each shrunk separately:
  whiff  P(miss | swing)
  xw     xwOBA on contact | ball in play
  su     squared-up | ball in play (needs bat tracking)
Whiff-adjusted contact quality CQ = (1 - whiff) * xw.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from scipy.spatial import cKDTree

from .savant import SwingRow, _f, approach_angle

# mode "shape": location + velo + IVB + HB + VAA (pitch type ignored, the shape carries it)
# mode "type":  location + pitch type label (the earlier, shape-blind model)
SHAPE_BW = np.array([0.30, 0.30, 3.0, 4.0, 4.0, 0.8])
TYPE_BW = np.array([0.30, 0.30, 1.0])
TYPE_GAP = 1000.0
_TYPES = ["FF", "SI", "FC", "SL", "ST", "SV", "CH", "FS", "CU", "KC", "CS", "SC", "KN", "EP", "FO"]
FASTBALLS = {"FF", "SI", "FC"}


def _type_code(pt: str) -> float:
    return float(_TYPES.index(pt) if pt in _TYPES else len(_TYPES)) * TYPE_GAP


def raw_swing(s: SwingRow, mode: str):
    if s.x_away is None:
        return None
    if mode == "type":
        return (s.x_away, s.z, _type_code(s.pitch_type))
    v = (s.x_away, s.z, s.velo, s.ivb, s.hb, s.vaa)
    return None if any(a is None for a in v) else v


def raw_query(mode: str, x: float, z: float, pt: str, velo: float, ivb: float, hb: float, vaa: float):
    return (x, z, _type_code(pt)) if mode == "type" else (x, z, velo, ivb, hb, vaa)


class _Local:
    """Gaussian-kernel local mean over the k nearest neighbours in scaled feature space."""

    def __init__(self, X: np.ndarray, y: np.ndarray, k: int):
        self.n = len(X)
        if self.n:
            self.tree = cKDTree(X)
            self.y = np.asarray(y, float)
            self.k = min(k, self.n)

    def sums(self, Q: np.ndarray):
        if not self.n:
            z = np.zeros(len(Q))
            return z, z
        d, i = self.tree.query(Q, k=self.k, workers=-1)
        if self.k == 1:
            d, i = d[:, None], i[:, None]
        w = np.exp(-0.5 * d * d)
        return (w * self.y[i]).sum(1), w.sum(1)


class ContactModel:
    """Kernel contact model. Effective sample sizes (k_*) are in kernel-weighted swings: a hitter's
    local estimate needs about that much nearby evidence to outweigh the league prior."""

    def __init__(self, hitter: Iterable[SwingRow], league: Iterable[SwingRow], mode: str = "shape",
                 k_whiff: float = 25.0, k_xw: float = 12.0, k_su: float = 12.0,
                 K_hitter: int = 80, K_league: int = 400, prior_m: float = 3.0):
        self.mode = mode
        self.bw = SHAPE_BW if mode == "shape" else TYPE_BW
        self.k = {"whiff": k_whiff, "foul": k_whiff, "xw": k_xw, "su": k_su}
        self.m = prior_m
        self._h = self._build(list(hitter), K_hitter)
        self._l = self._build(list(league), K_league)
        lg = list(league)
        self._g = {
            "whiff": float(np.mean([s.whiff for s in lg])) if lg else 0.25,
            "foul": float(np.mean([(not s.whiff and s.xwoba is None) for s in lg])) if lg else 0.35,
            "xw": float(np.mean([s.xwoba for s in lg if s.xwoba is not None] or [0.35])),
            "su": float(np.mean([s.squared_up for s in lg if s.squared_up is not None] or [0.3])),
        }

    def _build(self, rows: list[SwingRow], K: int) -> dict:
        feats = [(s, raw_swing(s, self.mode)) for s in rows]
        feats = [(s, f) for s, f in feats if f is not None]

        def sub(pred, yfn):
            pts = [(f, yfn(s)) for s, f in feats if pred(s)]
            X = np.array([p[0] for p in pts], float).reshape(-1, len(self.bw)) / self.bw
            return _Local(X, np.array([p[1] for p in pts], float), K)

        return {
            "whiff": sub(lambda s: True, lambda s: float(s.whiff)),
            "foul": sub(lambda s: True, lambda s: float(not s.whiff and s.xwoba is None)),
            "xw": sub(lambda s: s.xwoba is not None, lambda s: s.xwoba),
            "su": sub(lambda s: s.squared_up is not None, lambda s: float(s.squared_up)),
        }

    def predict(self, Q, use_hitter: bool = True) -> dict[str, np.ndarray]:
        Q = np.asarray(Q, float).reshape(-1, len(self.bw)) / self.bw
        out = {}
        for t in ("whiff", "foul", "xw", "su"):
            ls, lw = self._l[t].sums(Q)
            prior = (ls + self.m * self._g[t]) / (lw + self.m)
            if use_hitter:
                hs, hw = self._h[t].sums(Q)
                out[t] = (hs + self.k[t] * prior) / (hw + self.k[t])
            else:
                out[t] = prior
        over = np.maximum(out["whiff"] + out["foul"] - 0.98, 0.0)  # keep p_bip positive
        if over.any():
            scale = 1.0 - over / (out["whiff"] + out["foul"])
            out["whiff"], out["foul"] = out["whiff"] * scale, out["foul"] * scale
        return out

    def predict_pair(self, Q):
        """(league-only prediction, hitter-shrunk prediction), sharing the league prior work."""
        Qs = np.asarray(Q, float).reshape(-1, len(self.bw)) / self.bw
        lg, hit = {}, {}
        for t in ("whiff", "foul", "xw", "su"):
            ls, lw = self._l[t].sums(Qs)
            prior = (ls + self.m * self._g[t]) / (lw + self.m)
            hs, hw = self._h[t].sums(Qs)
            lg[t], hit[t] = prior, (hs + self.k[t] * prior) / (hw + self.k[t])
        for d in (lg, hit):
            over = np.maximum(d["whiff"] + d["foul"] - 0.98, 0.0)
            if over.any():
                sc = 1.0 - over / (d["whiff"] + d["foul"])
                d["whiff"], d["foul"] = d["whiff"] * sc, d["foul"] * sc
        return lg, hit

    def predict_cq(self, Q, use_hitter: bool = True) -> np.ndarray:
        p = self.predict(Q, use_hitter)
        return (1.0 - p["whiff"]) * p["xw"]

    def query_swings(self, swings: list[SwingRow]):
        """Feature matrix for swings that have every feature, plus the boolean mask of those kept."""
        raw = [raw_swing(s, self.mode) for s in swings]
        mask = np.array([r is not None for r in raw], bool)
        Q = np.array([r for r in raw if r is not None], float).reshape(-1, len(self.bw))
        return Q, mask


# ---------------------------------------------------------------- pitchers

@dataclass(frozen=True)
class PitchRow:
    pitcher: str
    date: str
    pitch_type: str
    tto: Optional[int]
    velo: Optional[float]
    ivb: Optional[float]
    hb: Optional[float]
    vaa: Optional[float]
    stand: str = ""


def parse_pitches(csv_text: str) -> list[PitchRow]:
    """Every pitch (not just swings), for building arsenals."""
    out = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        pt = row.get("pitch_type")
        if not pt:
            continue
        pfx_z = _f(row.get("pfx_z"))
        tto = _f(row.get("n_thruorder_pitcher"))
        out.append(PitchRow(
            pitcher=str(row.get("pitcher") or ""), date=row.get("game_date") or "", pitch_type=pt,
            tto=int(tto) if tto else None, velo=_f(row.get("release_speed")),
            ivb=pfx_z * 12.0 if pfx_z is not None else None, hb=_f(row.get("api_break_x_batter_in")),
            vaa=approach_angle(row), stand=(row.get("stand") or "").strip(),
        ))
    return out


@dataclass(frozen=True)
class ArsenalPitch:
    pitch_type: str
    usage: float
    velo: float
    ivb: float
    hb: float
    vaa: float
    n: int


def cap_tto(t: Optional[int]) -> Optional[int]:
    return None if t is None else min(t, 3)


def build_arsenal(pitches: Iterable[PitchRow], before: str, tto: Optional[int] = None,
                  min_usage: float = 0.05, min_n: int = 30, n0_shape: float = 25.0,
                  n0_usage: float = 60.0) -> dict[str, ArsenalPitch]:
    """One pitcher's arsenal from pitches before a date. With tto set, shape and usage are for that
    time through the order (3 means 3+), shrunk toward his all-innings average so a thin TTO sample
    does not swing the plan. Pass the pitcher's rows only."""
    rows = [p for p in pitches if p.date < before and None not in (p.velo, p.ivb, p.hb, p.vaa)]
    all_by = defaultdict(list)
    for p in rows:
        all_by[p.pitch_type].append(p)
    n_all = len(rows)
    if not n_all:
        return {}
    tto_rows = [p for p in rows if cap_tto(p.tto) == tto] if tto else []
    tto_by = defaultdict(list)
    for p in tto_rows:
        tto_by[p.pitch_type].append(p)

    def mean(ps, attr):
        return float(np.mean([getattr(p, attr) for p in ps]))

    out = {}
    for pt, ps in all_by.items():
        if len(ps) < min_n:
            continue
        ts = tto_by.get(pt, [])
        w = len(ts) / (len(ts) + n0_shape) if tto else 0.0
        shape = {a: (w * mean(ts, a) if ts else 0.0) + (1 - w) * mean(ps, a)
                 for a in ("velo", "ivb", "hb", "vaa")}
        u_all = len(ps) / n_all
        if tto and tto_rows:
            wu = len(tto_rows) / (len(tto_rows) + n0_usage)
            usage = wu * len(ts) / len(tto_rows) + (1 - wu) * u_all
        else:
            usage = u_all
        if usage >= min_usage:
            out[pt] = ArsenalPitch(pt, usage, shape["velo"], shape["ivb"], shape["hb"], shape["vaa"], len(ps))
    return out


def fit_tto_shifts(model: "ContactModel", swings: list[SwingRow]) -> dict[int, tuple[float, float]]:
    """Residual of the (league) model by time through the order, relative to the all-TTO mean:
    {tto: (whiff_shift, xwOBAcon_shift)}. Swings should be against starters, before any cutoff.
    Captures familiarity effects that pitch shape and location do not."""
    rows = [s for s in swings if s.tto]
    Q, mask = model.query_swings(rows)
    rows = [s for s, k in zip(rows, mask) if k]
    if not rows:
        return {1: (0.0, 0.0), 2: (0.0, 0.0), 3: (0.0, 0.0)}
    p = model.predict(Q, use_hitter=False)
    rw = np.array([float(s.whiff) for s in rows]) - p["whiff"]
    bip = np.array([s.xwoba is not None for s in rows])
    rx = np.array([s.xwoba if s.xwoba is not None else 0.0 for s in rows]) - p["xw"]
    t = np.array([cap_tto(s.tto) for s in rows])
    mw, mx = rw.mean(), rx[bip].mean()
    out = {}
    for k in (1, 2, 3):
        m = t == k
        out[k] = (float(rw[m].mean() - mw) if m.any() else 0.0,
                  float(rx[m & bip].mean() - mx) if (m & bip).any() else 0.0)
    return out
