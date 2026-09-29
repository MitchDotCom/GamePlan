"""Count-aware swing/take decision layer.

For a pitch in a cell, compare the expected value (wOBA scale) of swinging vs taking in the current
count. GO / NO_GO then depends on the count automatically: the same pitch is a better take at 0-0
than at 2 strikes, without hand-edited zone rules.

    swing = P(whiff) * V(after strike) + P(foul) * V(after foul) + P(bip) * xwOBAcon
    take  = P(called strike) * V(after strike) + (1 - P(called strike)) * V(after ball)

V(balls, strikes) is the expected final PA wOBA from that count, fit from data (or the default table).
Base-out, score and inning enter through SituationWeights, which reweights terminal outcomes. Those
weights are documented heuristics, not fitted; treat them as knobs to review with coaches.
"""
from __future__ import annotations

import csv
import io
import json
import math
import pathlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

# Rough expected final-PA wOBA by count (MLB, recent seasons). Replace with fit_count_values output.
DEFAULT_COUNT_VALUES = {
    (0, 0): 0.315, (1, 0): 0.345, (2, 0): 0.395, (3, 0): 0.500,
    (0, 1): 0.285, (1, 1): 0.310, (2, 1): 0.350, (3, 1): 0.450,
    (0, 2): 0.200, (1, 2): 0.215, (2, 2): 0.245, (3, 2): 0.340,
}
WALK_VALUE = 0.69
HBP_VALUE = 0.72
STRIKEOUT_VALUE = 0.0


@dataclass(frozen=True)
class CountValues:
    table: dict[tuple[int, int], float]
    walk: float = WALK_VALUE
    strikeout: float = STRIKEOUT_VALUE

    def after_ball(self, b: int, s: int) -> float:
        return self.walk if b + 1 >= 4 else self.table[(b + 1, s)]

    def after_strike(self, b: int, s: int) -> float:
        return self.strikeout if s + 1 >= 3 else self.table[(b, s + 1)]

    def after_foul(self, b: int, s: int) -> float:
        return self.table[(b, s)] if s >= 2 else self.table[(b, s + 1)]

    def to_json(self) -> str:
        return json.dumps({"table": {f"{b}-{s}": v for (b, s), v in self.table.items()},
                           "walk": self.walk, "strikeout": self.strikeout}, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "CountValues":
        d = json.loads(text)
        return cls({tuple(map(int, k.split("-"))): v for k, v in d["table"].items()}, d["walk"], d["strikeout"])


DEFAULT = CountValues(dict(DEFAULT_COUNT_VALUES))


def fit_count_values(csv_texts: Iterable[str]) -> CountValues:
    """Expected final PA wOBA for each count reached, from pitch-level rows (needs game_pk,
    at_bat_number, balls, strikes, events, woba_value). Plate appearances with no wOBA (e.g.
    sacrifices) are skipped. Pass many hitters or the table is noisy."""
    pas: dict[tuple, dict] = {}
    for text in csv_texts:
        for r in csv.DictReader(io.StringIO(text)):
            try:
                key = (r["game_pk"], r["at_bat_number"])
                b, s = int(r["balls"]), int(r["strikes"])
            except (KeyError, ValueError):
                continue
            pa = pas.setdefault(key, {"counts": set(), "woba": None, "ev": None})
            if b <= 3 and s <= 2:
                pa["counts"].add((b, s))
            if r.get("events"):
                pa["ev"] = r["events"]
                if r.get("woba_value") not in (None, ""):
                    pa["woba"] = float(r["woba_value"])
    sums: dict = defaultdict(lambda: [0.0, 0])
    walks, ks = [], []
    for pa in pas.values():
        if pa["woba"] is None:
            continue
        for c in pa["counts"]:
            sums[c][0] += pa["woba"]
            sums[c][1] += 1
        if pa["ev"] == "walk":
            walks.append(pa["woba"])
        if pa["ev"] in ("strikeout", "strikeout_double_play"):
            ks.append(pa["woba"])
    table = dict(DEFAULT_COUNT_VALUES)
    for c, (t, n) in sums.items():
        if n >= 200:
            table[c] = t / n
    return CountValues(table, sum(walks) / len(walks) if walks else WALK_VALUE,
                       sum(ks) / len(ks) if ks else STRIKEOUT_VALUE)


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


@dataclass(frozen=True)
class SituationWeights:
    """Reweights terminal outcomes for base-out / score / inning. Values are added to the outcome's
    wOBA-scale value. All zero = count-only decision. These are heuristics for coach review."""
    strikeout_extra: float = 0.0      # extra cost of a K (e.g. runner on 3rd, < 2 outs)
    contact_bonus: float = 0.0        # extra value of putting the ball in play
    walk_scale: float = 1.0           # walk value multiplier (1B open with a runner in scoring position, etc.)


def situation_weights(outs: int = 0, bases: tuple[bool, bool, bool] = (False, False, False),
                      score_diff: int = 0, inning: int = 1) -> SituationWeights:
    """bases = (on1B, on2B, on3B); score_diff = own score minus opponent."""
    on1, on2, on3 = bases
    k_extra = c_bonus = 0.0
    if on3 and outs < 2:
        k_extra += 0.10       # a run scores on many balls in play, a K wastes the chance
        c_bonus += 0.03
    if (on2 or on3) and outs == 2:
        c_bonus += 0.02       # any hit scores; walk-or-K equally unhelpful
    if on1 and not (on2 or on3) and outs < 2:
        k_extra += 0.02       # double-play risk makes contact less valuable, K modestly worse than an out
        c_bonus -= 0.02
    walk_scale = 1.0
    if inning >= 7 and abs(score_diff) <= 1:
        walk_scale = 0.9      # late and close: extra bases matter more than a free base, small effect
    return SituationWeights(k_extra, c_bonus, walk_scale)


@dataclass(frozen=True)
class PitchValue:
    swing_ev: float
    take_ev: float

    @property
    def delta(self) -> float:
        return self.swing_ev - self.take_ev


def pitch_value(p: dict[str, float], p_cs: float, balls: int, strikes: int,
                cv: CountValues = DEFAULT, w: SituationWeights = SituationWeights()) -> PitchValue:
    """p has predicted 'whiff', 'foul', 'xw' (xwOBA on contact) for this pitch and hitter."""
    k_val = cv.strikeout - w.strikeout_extra
    walk = cv.walk * w.walk_scale
    after_strike = k_val if strikes + 1 >= 3 else cv.table[(balls, strikes + 1)]
    after_ball = walk if balls + 1 >= 4 else cv.table[(balls + 1, strikes)]
    after_foul = cv.table[(balls, strikes)] if strikes >= 2 else cv.table[(balls, strikes + 1)]
    p_bip = max(1.0 - p["whiff"] - p["foul"], 0.0)
    swing = (p["whiff"] * after_strike + p["foul"] * after_foul
             + p_bip * (p["xw"] + w.contact_bonus))
    take = p_cs * after_strike + (1.0 - p_cs) * after_ball
    return PitchValue(swing, take)


GO_DELTA = 0.020       # swing beats take by >= .020 wOBA points
NO_GO_DELTA = -0.020


def classify(delta: float, go: float = GO_DELTA, no_go: float = NO_GO_DELTA) -> str:
    return "GO" if delta >= go else ("NO_GO" if delta <= no_go else "CONDITIONAL")
