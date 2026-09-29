"""Count-aware swing/take decision layer.

For a pitch in a cell, compare the expected value (wOBA scale) of swinging vs taking in the current
count. GO / NO_GO then depends on the count automatically: the same pitch is a better take at 0-0
than at 2 strikes, without hand-edited zone rules.

    swing = P(whiff) * V(after strike) + P(foul) * V(after foul) + P(bip) * xwOBAcon
    take  = P(called strike) * V(after strike) + (1 - P(called strike)) * V(after ball)

V(balls, strikes) is the expected final PA wOBA from that count, fit from data. Base-out state
changes what a strikeout, a walk and a ball in play are worth; those changes are fit from Statcast
run expectancy (baseout.py) and scaled by a coach-chosen SituationPolicy per spot. Score and inning
are not modelled yet: that needs a win-expectancy version of the same fit.
"""
from __future__ import annotations

import csv
import io
import json
import math
import pathlib
from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Optional

from . import baseout
from .constants import value as _const

# Fallback expected final-PA wOBA by count if no fitted table is packaged.
DEFAULT_COUNT_VALUES = {
    (0, 0): 0.315, (1, 0): 0.345, (2, 0): 0.395, (3, 0): 0.500,
    (0, 1): 0.285, (1, 1): 0.310, (2, 1): 0.350, (3, 1): 0.450,
    (0, 2): 0.200, (1, 2): 0.215, (2, 2): 0.245, (3, 2): 0.340,
}
WALK_VALUE = _const("WBB_2025")
HBP_VALUE = _const("WHBP_2025")
STRIKEOUT_VALUE = 0.0


@dataclass(frozen=True)
class CountValues:
    table: dict[tuple[int, int], float]
    walk: float = WALK_VALUE
    strikeout: float = STRIKEOUT_VALUE
    bip_bonus: float = 0.0     # added to a ball in play's value (set by situation)
    # P(final outcome is K, BB/HBP, ball in play | count reached); lets a situation shift the whole table.
    outcome_probs: dict[tuple[int, int], tuple[float, float, float]] = field(default_factory=dict)

    def after_ball(self, b: int, s: int) -> float:
        return self.walk if b + 1 >= 4 else self.table[(b + 1, s)]

    def after_strike(self, b: int, s: int) -> float:
        return self.strikeout if s + 1 >= 3 else self.table[(b, s + 1)]

    def after_foul(self, b: int, s: int) -> float:
        return self.table[(b, s)] if s >= 2 else self.table[(b, s + 1)]

    def to_json(self) -> str:
        return json.dumps({"table": {f"{b}-{s}": v for (b, s), v in self.table.items()},
                           "walk": self.walk, "strikeout": self.strikeout,
                           "outcome_probs": {f"{b}-{s}": list(v) for (b, s), v in self.outcome_probs.items()}},
                          indent=1)

    @classmethod
    def from_json(cls, text: str) -> "CountValues":
        d = json.loads(text)
        parse = lambda k: tuple(map(int, k.split("-")))
        return cls({parse(k): v for k, v in d["table"].items()}, d["walk"], d["strikeout"],
                   0.0, {parse(k): tuple(v) for k, v in d.get("outcome_probs", {}).items()})


def _load_default() -> CountValues:
    p = pathlib.Path(__file__).with_name("count_values_2025.json")
    return CountValues.from_json(p.read_text()) if p.exists() else CountValues(dict(DEFAULT_COUNT_VALUES))


DEFAULT = _load_default()


def fit_count_values(csv_texts: Iterable[str]) -> CountValues:
    """Expected final PA wOBA for each count reached, plus how plate appearances passing through it
    end, from pitch-level rows (needs game_pk, at_bat_number, balls, strikes, events, woba_value).
    Plate appearances with no wOBA (e.g. sacrifices) are skipped. Pass many hitters."""
    pas: dict[tuple, dict] = {}
    for text in csv_texts:
        for r in csv.DictReader(io.StringIO(text)):
            try:
                key = (r["game_pk"], r["at_bat_number"])
                b, s = int(r["balls"]), int(r["strikes"])
            except (KeyError, ValueError):
                continue
            pa = pas.setdefault(key, {"counts": set(), "woba": None, "ev": None, "bunt": False})
            if "bunt" in (r.get("description") or "") or "bunt" in (r.get("events") or ""):
                pa["bunt"] = True
            if b <= 3 and s <= 2:
                pa["counts"].add((b, s))
            if r.get("events"):
                pa["ev"] = r["events"]
                if r.get("woba_value") not in (None, ""):
                    pa["woba"] = float(r["woba_value"])
    sums: dict = defaultdict(lambda: [0.0, 0, 0, 0, 0])   # wOBA sum, n, nK, nBB, nBIP
    walks, ks = [], []
    for pa in pas.values():
        if pa["woba"] is None or pa["bunt"]:
            continue
        cls = baseout.outcome_class(pa["ev"] or "")
        for c in pa["counts"]:
            a = sums[c]
            a[0] += pa["woba"]
            a[1] += 1
            if cls:
                a[2 + ("K", "BB", "BIP").index(cls)] += 1
        if pa["ev"] == "walk":
            walks.append(pa["woba"])
        if pa["ev"] in baseout.K_EVENTS:
            ks.append(pa["woba"])
    table = dict(DEFAULT_COUNT_VALUES)
    probs = {}
    for c, a in sums.items():
        if a[1] >= 200:
            table[c] = a[0] / a[1]
            tot = max(a[2] + a[3] + a[4], 1)
            probs[c] = (a[2] / tot, a[3] / tot, a[4] / tot)
    return CountValues(table, sum(walks) / len(walks) if walks else WALK_VALUE,
                       sum(ks) / len(ks) if ks else STRIKEOUT_VALUE, 0.0, probs)


def p_called_strike(x_away: float, z: float, sz_bot: float = 1.5, sz_top: float = 3.5,
                    half_plate_ft: float = 0.83, scale_in: float = 1.1) -> float:
    """Stand-in for the called-strike surface: logistic in inches outside the zone edge.
    Replace with a fit on taken pitches (and the game's umpire) when that data is loaded."""
    dx = max(abs(x_away) - half_plate_ft, 0.0)
    dz = max(sz_bot - z, 0.0, z - sz_top)
    d_in = math.hypot(dx, dz) * 12.0
    inside = abs(x_away) <= half_plate_ft and sz_bot <= z <= sz_top
    signed = -min((half_plate_ft - abs(x_away)), z - sz_bot, sz_top - z) * 12.0 if inside else d_in
    return 1.0 / (1.0 + math.exp(signed / scale_in))


# ------------------------------------------------------------------ situation

class SituationPolicy(str, Enum):
    """How hard a coach wants a base-out spot to bend the plan away from the hitter's damage zone.
    Scale is a fraction of the empirical run-value change for that state."""
    OFF = "OFF"                      # count-only decision
    MILD = "MILD"                    # half of the fitted change
    STRONG = "STRONG"                # the full fitted change
    CONTACT_FIRST = "CONTACT_FIRST"  # full change, and a GO also needs a low predicted whiff rate


_POLICY_SCALE = {SituationPolicy.OFF: 0.0, SituationPolicy.MILD: 0.5,
                 SituationPolicy.STRONG: 1.0, SituationPolicy.CONTACT_FIRST: 1.0}
CONTACT_FIRST_MAX_WHIFF = 0.22
SHRINK_N = 100.0                     # states with few PAs are pulled toward no adjustment: n / (n + 100)


class Spot(str, Enum):
    RUNNER_THIRD_LT2 = "RUNNER_THIRD_LT2"
    RISP_TWO_OUTS = "RISP_TWO_OUTS"
    DOUBLE_PLAY = "DOUBLE_PLAY"      # runner on first only, fewer than two outs
    OTHER = "OTHER"


def spot_of(outs: int, bases: tuple[bool, bool, bool]) -> Spot:
    on1, on2, on3 = bases
    if on3 and outs < 2:
        return Spot.RUNNER_THIRD_LT2
    if (on2 or on3) and outs == 2:
        return Spot.RISP_TWO_OUTS
    if on1 and not (on2 or on3) and outs < 2:
        return Spot.DOUBLE_PLAY
    return Spot.OTHER


@dataclass(frozen=True)
class SituationConfig:
    """Coach-switchable policy per spot. Set per hitter and per opposing starter, or take the model
    recommendation from matchup.recommend_policy."""
    runner_third_lt2: SituationPolicy = SituationPolicy.MILD
    risp_two_outs: SituationPolicy = SituationPolicy.MILD
    runner_first_lt2: SituationPolicy = SituationPolicy.MILD     # double-play spot
    other_states: SituationPolicy = SituationPolicy.OFF
    score_inning: SituationPolicy = SituationPolicy.OFF    # lead x inning effect; did not validate (V3), off by default
    contact_first_max_whiff: float = CONTACT_FIRST_MAX_WHIFF

    def policy_for(self, spot: Spot) -> SituationPolicy:
        return {Spot.RUNNER_THIRD_LT2: self.runner_third_lt2, Spot.RISP_TWO_OUTS: self.risp_two_outs,
                Spot.DOUBLE_PLAY: self.runner_first_lt2, Spot.OTHER: self.other_states}[spot]


_CONFIG_FIELDS = ("runner_third_lt2", "risp_two_outs", "runner_first_lt2", "other_states", "score_inning",
                  "contact_first_max_whiff")


@dataclass(frozen=True)
class SituationOverride:
    """Sets only the fields a coach wants to change; None means inherit."""
    runner_third_lt2: Optional[SituationPolicy] = None
    risp_two_outs: Optional[SituationPolicy] = None
    runner_first_lt2: Optional[SituationPolicy] = None
    other_states: Optional[SituationPolicy] = None
    score_inning: Optional[SituationPolicy] = None
    contact_first_max_whiff: Optional[float] = None

    def apply(self, base: SituationConfig) -> SituationConfig:
        return replace(base, **{f: getattr(self, f) for f in _CONFIG_FIELDS if getattr(self, f) is not None})


@dataclass(frozen=True)
class PolicyBook:
    """Situation policies at four levels: team default, per opposing starter, per hitter, and per
    hitter-vs-starter pair. Later levels in `precedence` override earlier ones field by field, so a
    starter-wide 'contact-first with a runner on third' can be relaxed for one hitter who rarely
    strikes out, and tightened again for one specific matchup."""
    default: SituationConfig = SituationConfig()
    by_starter: dict[str, SituationOverride] = field(default_factory=dict)
    by_hitter: dict[str, SituationOverride] = field(default_factory=dict)
    by_pair: dict[str, SituationOverride] = field(default_factory=dict)   # key "hitter_id|starter_id"
    precedence: tuple[str, ...] = ("starter", "hitter", "pair")            # last wins

    def _layers(self, hitter_id: str, starter_id: str):
        src = {"starter": self.by_starter.get(starter_id), "hitter": self.by_hitter.get(hitter_id),
               "pair": self.by_pair.get(f"{hitter_id}|{starter_id}")}
        return [(name, src[name]) for name in self.precedence if src.get(name) is not None]

    def resolve(self, hitter_id: str, starter_id: str) -> SituationConfig:
        cfg = self.default
        for _, ov in self._layers(hitter_id, starter_id):
            cfg = ov.apply(cfg)
        return cfg

    def explain(self, hitter_id: str, starter_id: str) -> dict[str, str]:
        """Which level set each field, for the coach to see why a plan is what it is."""
        out = {f: "default" for f in _CONFIG_FIELDS}
        for name, ov in self._layers(hitter_id, starter_id):
            for f in _CONFIG_FIELDS:
                if getattr(ov, f) is not None:
                    out[f] = name
        return out

    def to_json(self) -> str:
        enc = lambda o: {f: (getattr(o, f).value if isinstance(getattr(o, f), Enum) else getattr(o, f))
                         for f in _CONFIG_FIELDS if getattr(o, f) is not None}
        return json.dumps({"default": enc(self.default),
                           "by_starter": {k: enc(v) for k, v in self.by_starter.items()},
                           "by_hitter": {k: enc(v) for k, v in self.by_hitter.items()},
                           "by_pair": {k: enc(v) for k, v in self.by_pair.items()},
                           "precedence": list(self.precedence)}, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "PolicyBook":
        d = json.loads(text)

        def dec(m, klass):
            return klass(**{k: (SituationPolicy(v) if k != "contact_first_max_whiff" else v) for k, v in m.items()})
        return cls(dec(d.get("default", {}), SituationConfig),
                   {k: dec(v, SituationOverride) for k, v in d.get("by_starter", {}).items()},
                   {k: dec(v, SituationOverride) for k, v in d.get("by_hitter", {}).items()},
                   {k: dec(v, SituationOverride) for k, v in d.get("by_pair", {}).items()},
                   tuple(d.get("precedence", ("starter", "hitter", "pair"))))


@dataclass(frozen=True)
class SituationWeights:
    """Additive changes to terminal outcome values (wOBA scale) for one base-out state."""
    d_k: float = 0.0
    d_bb: float = 0.0
    d_bip: float = 0.0
    max_whiff: Optional[float] = None  # CONTACT_FIRST: a GO needs predicted whiff <= this


_BASEOUT = None
_SCOREINNING = None
MIN_LEVERAGE = 0.04     # win probability per run below which a lead x inning bucket is a blowout: no adjustment


def situation_weights(outs: int = 0, bases: tuple[bool, bool, bool] = (False, False, False),
                      score_diff: int = 0, inning: int = 1,
                      config: SituationConfig = SituationConfig(), table: Optional[dict] = None,
                      si_table: Optional[dict] = None) -> SituationWeights:
    """bases = (on1B, on2B, on3B); score_diff = batting team's lead. Two independent effects add:
    the base-out state (per-spot policy) and the lead x inning context (score_inning policy)."""
    global _BASEOUT, _SCOREINNING
    spot = spot_of(outs, bases)
    policy = config.policy_for(spot)
    scale = _POLICY_SCALE[policy]
    d = {"K": 0.0, "BB": 0.0, "BIP": 0.0}
    if scale:
        if table is None:
            _BASEOUT = _BASEOUT if _BASEOUT is not None else baseout.load()
            table = _BASEOUT
        entry = table.get("states", {}).get(baseout.state_key(outs, *bases), {})
        for cls in d:
            v, n = entry.get(cls, [0.0, 0])
            d[cls] += scale * v * n / (n + SHRINK_N)
    si_scale = _POLICY_SCALE[config.score_inning]
    if si_scale:
        if si_table is None:
            _SCOREINNING = _SCOREINNING if _SCOREINNING is not None else baseout.load_score_inning()
            si_table = _SCOREINNING
        key = baseout.si_key(score_diff, inning)
        if si_table.get("leverage_wpa_per_run", {}).get(key, 0.0) >= MIN_LEVERAGE:
            entry = si_table.get("buckets", {}).get(key, {})
            for cls in d:
                v, n = entry.get(cls, [0.0, 0])
                d[cls] += si_scale * v * n / (n + SHRINK_N)
    contact_first = policy is SituationPolicy.CONTACT_FIRST or config.score_inning is SituationPolicy.CONTACT_FIRST
    return SituationWeights(d["K"], d["BB"], d["BIP"], config.contact_first_max_whiff if contact_first else None)


def apply_situation(cv: CountValues, w: SituationWeights) -> CountValues:
    """Shift terminal values, and every count's expected value by how its plate appearances end."""
    if not (w.d_k or w.d_bb or w.d_bip):
        return cv
    table = {}
    for c, v in cv.table.items():
        pk, pbb, pbip = cv.outcome_probs.get(c, (0.0, 0.0, 0.0))
        table[c] = v + pk * w.d_k + pbb * w.d_bb + pbip * w.d_bip
    return replace(cv, table=table, walk=cv.walk + w.d_bb, strikeout=cv.strikeout + w.d_k,
                   bip_bonus=cv.bip_bonus + w.d_bip)


# ------------------------------------------------------------------ pitch value

@dataclass(frozen=True)
class PitchValue:
    swing_ev: float
    take_ev: float

    @property
    def delta(self) -> float:
        return self.swing_ev - self.take_ev


def pitch_value(p: dict[str, float], p_cs: float, balls: int, strikes: int,
                cv: CountValues = DEFAULT) -> PitchValue:
    """p has predicted 'whiff', 'foul', 'xw' (xwOBA on contact) for this pitch and hitter. For a
    situation, pass cv through apply_situation first."""
    after_strike = cv.after_strike(balls, strikes)
    after_ball = cv.after_ball(balls, strikes)
    after_foul = cv.after_foul(balls, strikes)
    p_bip = max(1.0 - p["whiff"] - p["foul"], 0.0)
    swing = p["whiff"] * after_strike + p["foul"] * after_foul + p_bip * (p["xw"] + cv.bip_bonus)
    take = p_cs * after_strike + (1.0 - p_cs) * after_ball
    return PitchValue(swing, take)


GO_DELTA = 0.020       # swing beats take by >= .020 wOBA points
NO_GO_DELTA = -0.020


def classify(delta: float, go: float = GO_DELTA, no_go: float = NO_GO_DELTA) -> str:
    return "GO" if delta >= go else ("NO_GO" if delta <= no_go else "CONDITIONAL")


def realized_value(swing: bool, whiff: bool, xwoba: Optional[float], take_call: str, balls: int,
                   strikes: int, cv: CountValues = DEFAULT) -> Optional[float]:
    """wOBA-scale value of the state a pitch actually led to. None when it cannot be valued (a foul
    is valued as the count it leaves; a ball in play needs its xwOBA)."""
    if swing:
        if whiff:
            return cv.after_strike(balls, strikes)
        if xwoba is None:
            return cv.after_foul(balls, strikes)
        return xwoba
    if take_call == "strike":
        return cv.after_strike(balls, strikes)
    if take_call == "ball":
        return cv.after_ball(balls, strikes)
    if take_call == "hbp":
        return HBP_VALUE
    return None


def evs_np(whiff, foul, xw, p_cs, balls, strikes, cv: CountValues = DEFAULT):
    """Vectorised (swing EV, take EV). Arrays of equal length. Pass cv through apply_situation for a spot."""
    import numpy as np
    tab = np.zeros((5, 4))
    for (b, s), v in cv.table.items():
        tab[b, s] = v
    b, s = np.asarray(balls, int), np.asarray(strikes, int)
    after_strike = np.where(s + 1 >= 3, cv.strikeout, tab[b, np.minimum(s + 1, 3)])
    after_ball = np.where(b + 1 >= 4, cv.walk, tab[np.minimum(b + 1, 4), s])
    after_foul = np.where(s >= 2, tab[b, s], tab[b, np.minimum(s + 1, 3)])
    p_bip = np.maximum(1.0 - whiff - foul, 0.0)
    swing = whiff * after_strike + foul * after_foul + p_bip * (xw + cv.bip_bonus)
    take = p_cs * after_strike + (1.0 - p_cs) * after_ball
    return swing, take


def deltas_np(whiff, foul, xw, p_cs, balls, strikes, cv: CountValues = DEFAULT):
    """Vectorised swing-minus-take."""
    swing, take = evs_np(whiff, foul, xw, p_cs, balls, strikes, cv)
    return swing - take
