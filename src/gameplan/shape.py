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
from enum import Enum
from typing import Iterable, Optional

import numpy as np
from scipy.spatial import cKDTree

from .constants import value as _const
from .savant import SwingRow, _f, approach_angle

# Feature ladders, from what a low-tier park with only basic tracking could provide up to full shape:
#   loc       location only
#   type      location + pitch type label (the earlier, shape-blind model)
#   typevelo  location + pitch type + velocity
#   shape     location + velocity + IVB + HB + VAA (pitch type ignored, the shape carries it)
SHAPE_BW = np.array([0.30, 0.30, 3.0, 4.0, 4.0, 0.8])
TYPE_BW = np.array([0.30, 0.30, 1.0])
LOC_BW = np.array([0.30, 0.30])
TYPEVELO_BW = np.array([0.30, 0.30, 1.0, 3.0])
MODE_BW = {"loc": LOC_BW, "type": TYPE_BW, "typevelo": TYPEVELO_BW, "shape": SHAPE_BW}
TYPE_GAP = 1000.0
_TYPES = ["FF", "SI", "FC", "SL", "ST", "SV", "CH", "FS", "CU", "KC", "CS", "SC", "KN", "EP", "FO"]
FASTBALLS = {"FF", "SI", "FC"}


def _type_code(pt: str) -> float:
    return float(_TYPES.index(pt) if pt in _TYPES else len(_TYPES)) * TYPE_GAP


def raw_swing(s: SwingRow, mode: str):
    if s.x_away is None:
        return None
    if mode == "loc":
        return (s.x_away, s.z)
    if mode == "type":
        return (s.x_away, s.z, _type_code(s.pitch_type))
    if mode == "typevelo":
        return None if s.velo is None else (s.x_away, s.z, _type_code(s.pitch_type), s.velo)
    v = (s.x_away, s.z, s.velo, s.ivb, s.hb, s.vaa)
    return None if any(a is None for a in v) else v


def raw_query(mode: str, x: float, z: float, pt: str, velo: float, ivb: float, hb: float, vaa: float):
    if mode == "loc":
        return (x, z)
    if mode == "type":
        return (x, z, _type_code(pt))
    if mode == "typevelo":
        return (x, z, _type_code(pt), velo)
    return (x, z, velo, ivb, hb, vaa)


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
                 K_hitter: int = 80, K_league: int = 400, prior_m: float = 3.0,
                 xw_attr: str = "xwoba", bw_scale: float = 1.0,
                 k_global_whiff: float = _const("K_GLOBAL_WHIFF"), k_global_xw: float = _const("K_GLOBAL_XW")):
        """xw_attr: which per-swing value the quality target uses. "xwoba" needs exit velo and launch
        angle; "woba" (actual outcome value) is the fallback for parks with no batted-ball tracking."""
        self.mode = mode
        self.xw_attr = xw_attr
        self.bw = MODE_BW[mode] * bw_scale
        self.k = {"whiff": k_whiff, "foul": k_whiff, "xw": k_xw, "su": k_su}
        self.m = prior_m
        self._rows = list(hitter)
        self._h = self._build(self._rows, K_hitter)
        self._l = self._build(list(league), K_league)
        lg = list(league)
        self.k_global = {"whiff": k_global_whiff, "xw": k_global_xw}
        self.offset = {"whiff": 0.0, "xw": 0.0, "foul": 0.0, "su": 0.0}
        self._g = {
            "whiff": float(np.mean([s.whiff for s in lg])) if lg else 0.25,
            "foul": float(np.mean([(not s.whiff and s.xwoba is None) for s in lg])) if lg else 0.35,
            "xw": float(np.mean([getattr(s, xw_attr) for s in lg if getattr(s, xw_attr) is not None] or [0.35])),
            "su": float(np.mean([s.squared_up for s in lg if s.squared_up is not None] or [0.3])),
        }
        if lg and self._rows:
            self.fit_offsets()

    @classmethod
    def for_hitter(cls, hitter_rows: Iterable[SwingRow], league_model: "ContactModel", **kw) -> "ContactModel":
        """One hitter's model that reuses an already-built league model's trees (building the league
        trees is the expensive part) and computes his hitter-level offsets against them."""
        m = cls(hitter_rows, [], mode=league_model.mode, xw_attr=league_model.xw_attr, **kw)
        m._l, m._g = league_model._l, league_model._g
        m.fit_offsets()
        return m

    def fit_offsets(self, hitter_rows: Iterable[SwingRow] | None = None) -> None:
        """Hitter-level term: how far the hitter runs from the league prior across all his swings, shrunk
        toward zero with k_global (empirical-Bayes two-level model). Call again if the league trees were
        swapped in after construction. Adds to the league prior before local shrinkage."""
        rows = list(hitter_rows if hitter_rows is not None else getattr(self, "_rows", []))
        self.offset = {"whiff": 0.0, "xw": 0.0, "foul": 0.0, "su": 0.0}
        rows = [r for r in rows if raw_swing(r, self.mode) is not None]
        if not rows:
            return
        Q = np.array([raw_swing(r, self.mode) for r in rows], float).reshape(-1, len(self.bw)) / self.bw
        ls, lw = self._l["whiff"].sums(Q)
        prior_w = (ls + self.m * self._g["whiff"]) / (lw + self.m)
        y_w = np.array([float(r.whiff) for r in rows])
        self.offset["whiff"] = float((y_w - prior_w).sum() / (len(rows) + self.k_global["whiff"]))
        bip = [k for k, r in enumerate(rows) if getattr(r, self.xw_attr) is not None]
        if bip:
            ls, lw = self._l["xw"].sums(Q[bip])
            prior_x = (ls + self.m * self._g["xw"]) / (lw + self.m)
            y_x = np.array([getattr(rows[k], self.xw_attr) for k in bip])
            self.offset["xw"] = float((y_x - prior_x).sum() / (len(bip) + self.k_global["xw"]))

    def _build(self, rows: list[SwingRow], K: int) -> dict:
        feats = [(s, raw_swing(s, self.mode)) for s in rows]
        feats = [(s, f) for s, f in feats if f is not None]

        def sub(pred, yfn):
            pts = [(f, yfn(s)) for s, f in feats if pred(s)]
            X = np.array([p[0] for p in pts], float).reshape(-1, len(self.bw)) / self.bw
            return _Local(X, np.array([p[1] for p in pts], float), K)

        return {
            "whiff": sub(lambda s: True, lambda s: float(s.whiff)),
            "foul": sub(lambda s: True, lambda s: float(not s.whiff and getattr(s, self.xw_attr) is None)),
            "xw": sub(lambda s: getattr(s, self.xw_attr) is not None, lambda s: getattr(s, self.xw_attr)),
            "su": sub(lambda s: s.squared_up is not None, lambda s: float(s.squared_up)),
        }

    def predict(self, Q, use_hitter: bool = True, coach=None) -> dict[str, np.ndarray]:
        """coach: optional coach.CoachProfile; its adjustments move the league prior before the
        hitter's own swings shrink toward it, so they fade as real data accumulates."""
        raw = np.asarray(Q, float).reshape(-1, len(self.bw))
        Q = raw / self.bw
        adj = coach.adjust(raw, self.mode) if coach is not None else None
        out = {}
        for t in ("whiff", "foul", "xw", "su"):
            ls, lw = self._l[t].sums(Q)
            prior = (ls + self.m * self._g[t]) / (lw + self.m)
            if adj is not None and t in adj:
                prior = prior + adj[t]
            if use_hitter:
                hs, hw = self._h[t].sums(Q)
                prior_h = prior + self.offset.get(t, 0.0)
                out[t] = (hs + self.k[t] * prior_h) / (hw + self.k[t])
            else:
                out[t] = prior
        over = np.maximum(out["whiff"] + out["foul"] - 0.98, 0.0)  # keep p_bip positive
        if over.any():
            scale = 1.0 - over / (out["whiff"] + out["foul"])
            out["whiff"], out["foul"] = out["whiff"] * scale, out["foul"] * scale
        return out

    def support(self, Q) -> dict[str, np.ndarray]:
        """Kernel-weighted count of the hitter's own swings near each query (whiff target: all swings;
        xw target: balls in play). The information behind a hitter-specific estimate is this plus the
        pseudo-count of the league prior."""
        Qs = np.asarray(Q, float).reshape(-1, len(self.bw)) / self.bw
        return {"whiff": self._h["whiff"].sums(Qs)[1], "xw": self._h["xw"].sums(Qs)[1]}

    def predict_pair(self, Q, coach=None):
        """(league-only prediction, hitter-shrunk prediction), sharing the league prior work."""
        raw = np.asarray(Q, float).reshape(-1, len(self.bw))
        Qs = raw / self.bw
        adj = coach.adjust(raw, self.mode) if coach is not None else None
        lg, hit = {}, {}
        for t in ("whiff", "foul", "xw", "su"):
            ls, lw = self._l[t].sums(Qs)
            prior = (ls + self.m * self._g[t]) / (lw + self.m)
            if adj is not None and t in adj:
                prior = prior + adj[t]
            hs, hw = self._h[t].sums(Qs)
            lg[t], hit[t] = prior, (hs + self.k[t] * (prior + self.offset.get(t, 0.0))) / (hw + self.k[t])
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
    game_pk: str = ""
    at_bat: int = 0
    pitch_no: int = 0
    pitch_count: int = 0                 # this pitcher's pitch number in the game (1-based)
    days_rest: Optional[float] = None
    balls: int = 0
    strikes: int = 0
    prior_pa: Optional[int] = None       # this batter's earlier PAs vs this pitcher today
    fb_delta: Optional[float] = None     # rolling fastball velo minus his first-15 fastballs today
    inning: Optional[int] = None
    x_away: Optional[float] = None       # plate_x, + = away from the batter
    z: Optional[float] = None


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
            game_pk=str(row.get("game_pk") or ""), at_bat=int(_f(row.get("at_bat_number")) or 0),
            pitch_no=int(_f(row.get("pitch_number")) or 0),
            balls=int(_f(row.get("balls")) or 0), strikes=int(_f(row.get("strikes")) or 0),
            days_rest=_f(row.get("pitcher_days_since_prev_game")),
            prior_pa=int(_f(row.get("n_priorpa_thisgame_player_at_bat"))) if _f(row.get("n_priorpa_thisgame_player_at_bat")) is not None else None,
            inning=int(_f(row.get("inning"))) if _f(row.get("inning")) is not None else None,
            x_away=(_f(row.get("plate_x")) if (row.get("stand") or "").strip() == "R" else
                    (-_f(row.get("plate_x")) if _f(row.get("plate_x")) is not None else None)),
            z=_f(row.get("plate_z")),
        ))
    return _add_game_state(out)


def _add_game_state(rows: list[PitchRow]) -> list[PitchRow]:
    """Per pitcher-game: cumulative pitch count and a rolling fastball-velo drift. The drift is only
    defined from the 26th fastball (baseline = first 15, window = previous 10)."""
    from dataclasses import replace
    by_game = defaultdict(list)
    for r in rows:
        by_game[(r.pitcher, r.game_pk)].append(r)
    out = []
    for grp in by_game.values():
        grp.sort(key=lambda r: (r.at_bat, r.pitch_no))
        fb_v: list[float] = []
        base = None
        for n, r in enumerate(grp, 1):
            delta = None
            if len(fb_v) >= 25:
                base = base if base is not None else float(np.mean(fb_v[:15]))
                delta = float(np.mean(fb_v[-10:])) - base
            out.append(replace(r, pitch_count=n, fb_delta=delta))
            if r.pitch_type in FASTBALLS and r.velo:
                fb_v.append(r.velo)
    return out


def filter_starts(rows: list[PitchRow]) -> list[PitchRow]:
    """Keep only pitcher-games that began in the 1st inning (starts). Relief outings are dropped so
    arsenals, TTO and pitch-count states describe starters only."""
    first: dict[tuple, tuple] = {}
    for r in rows:
        k = (r.pitcher, r.game_pk)
        if k not in first or (r.at_bat, r.pitch_no) < first[k][0]:
            first[k] = ((r.at_bat, r.pitch_no), r.inning)
    return [r for r in rows if first[(r.pitcher, r.game_pk)][1] == 1]


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


def pitch_count_bin(n: int) -> int:
    """1: pitches 1-30, 2: 31-60, 3: 61-90, 4: 91+."""
    return 1 if n <= 30 else 2 if n <= 60 else 3 if n <= 90 else 4


class ArsenalBasis(str, Enum):
    """What the starter's arsenal is conditioned on. The 2025 study cannot separate TTO from pitch
    count (correlation .94), so this is a coach / analyst switch, not a settled answer."""
    ALL_INNINGS = "ALL_INNINGS"
    TTO = "TTO"
    PITCH_COUNT = "PITCH_COUNT"


@dataclass(frozen=True)
class PitcherState:
    """Everything known about the starter at this moment. Recorded on every plan snapshot whether or
    not the current basis uses it."""
    tto: int = 1
    pitch_count: int = 0
    fb_drift: Optional[float] = None    # rolling fastball velo minus his first-15 today, mph
    prior_pa: int = 0                   # this batter's earlier PAs vs him today
    days_rest: Optional[float] = None
    inning: int = 1


# Additive shifts on the hitter's predicted (whiff, xwOBAcon) by TTO, from the 2025 TTO-only
# regression on 52 starters (hitters whiff less; contact quality change is not distinguishable from 0).
TTO_EFFECT_2025 = {1: (0.0, 0.0), 2: (-0.010, 0.008), 3: (-0.016, 0.014)}


def build_arsenal(pitches: Iterable[PitchRow], before: str, tto: Optional[int] = None,
                  min_usage: float = 0.05, min_n: int = 30, n0_shape: float = 25.0,
                  n0_usage: float = 60.0, pc_bin: Optional[int] = None,
                  stand: Optional[str] = None, strikes: Optional[int] = None) -> dict[str, ArsenalPitch]:
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
    if tto:
        tto_rows = [p for p in rows if cap_tto(p.tto) == tto]
    elif pc_bin:
        tto_rows = [p for p in rows if p.pitch_count and pitch_count_bin(p.pitch_count) == pc_bin]
    else:
        tto_rows = []
    tto = tto or pc_bin
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
        # Usage also depends on the batter's side and the strike count (more breaking balls at two
        # strikes, different mixes to lefties); each is shrunk toward the usage so far.
        for keep, n0 in ((lambda p: stand and p.stand == stand, n0_usage),
                         (lambda p: strikes is not None and p.strikes == strikes, n0_usage)):
            sub = [p for p in rows if keep(p)]
            if sub:
                w = len(sub) / (len(sub) + n0)
                usage = w * sum(p.pitch_type == pt for p in sub) / len(sub) + (1 - w) * usage
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


def apply_live_drift(arsenal: dict[str, ArsenalPitch], fb_drift: Optional[float],
                     pass_through: float = 1.0) -> dict[str, ArsenalPitch]:
    """Shift every pitch's velocity by the starter's measured fastball drift today. Assumes all pitch
    types lose velocity together (pass_through=1); lower it if breaking balls hold their velocity."""
    from dataclasses import replace
    if not fb_drift:
        return arsenal
    return {k: replace(a, velo=a.velo + fb_drift * pass_through) for k, a in arsenal.items()}


def arsenal_for_state(pitches: Iterable[PitchRow], before: str, state: PitcherState,
                      basis: ArsenalBasis = ArsenalBasis.TTO, use_live_drift: bool = False,
                      **kw) -> dict[str, ArsenalPitch]:
    pitches = list(pitches)
    # kw may carry stand= (batter side) and strikes= (0, 1, 2) for usage
    if basis is ArsenalBasis.TTO:
        ars = build_arsenal(pitches, before, tto=cap_tto(state.tto), **kw)
    elif basis is ArsenalBasis.PITCH_COUNT:
        ars = build_arsenal(pitches, before, pc_bin=pitch_count_bin(max(state.pitch_count, 1)), **kw)
    else:
        ars = build_arsenal(pitches, before, **kw)
    return apply_live_drift(ars, state.fb_drift) if use_live_drift else ars
