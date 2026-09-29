"""Coach-report priors: turn hitting-coach scouting into a starting belief about a hitter, for parks
and levels where there is little tracking data.

A report is a set of tags. Each tag says: for this pitch family and region, this hitter is worse or
better than a typical hitter at missing (whiff) or at damage on contact (xwOBAcon), with a
confidence. The tags shift the league prior in the ContactModel; the hitter's own tracked swings then
pull the estimate toward what the data says, so a report matters most early in a season and fades
as swings accumulate. Coach accuracy is unknown: see study Test 7 for how accurate reports must be
to help. Requires model mode 'type' (pitch family comes from the type label).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

FAMILIES = {
    "FB": {"FF", "SI", "FC"},
    "BRK": {"SL", "ST", "SV", "CU", "KC", "CS", "SC"},
    "OFF": {"CH", "FS", "FO", "KN", "EP"},
}
FAMILY_OF = {t: f for f, ts in FAMILIES.items() for t in ts}
VERT_CUTS = (2.17, 2.83)     # thirds of a 1.5 - 3.5 ft zone
HORIZ_CUTS = (-0.28, 0.28)   # x_away: inside / middle / away
CONF_WEIGHT = {1: 0.4, 2: 0.7, 3: 1.0}
_TYPE_GAP = 1000.0


def vert_region(z: float) -> str:
    return "LOW" if z < VERT_CUTS[0] else ("HIGH" if z > VERT_CUTS[1] else "MID")


def horiz_region(x_away: float) -> str:
    return "IN" if x_away < HORIZ_CUTS[0] else ("AWAY" if x_away > HORIZ_CUTS[1] else "MID")


@dataclass(frozen=True)
class CoachTag:
    family: Optional[str] = None       # "FB" | "BRK" | "OFF" | None = all
    vert: Optional[str] = None         # "LOW" | "MID" | "HIGH" | None = all
    horiz: Optional[str] = None        # "IN" | "MID" | "AWAY" | None = all
    whiff_delta: float = 0.0           # + means he misses more (probability points per swing)
    contact_delta: float = 0.0         # + means better damage on contact (xwOBA points)
    confidence: int = 2                # 1 low, 2 medium, 3 high

    def matches(self, family: str, vert: str, horiz: str) -> bool:
        return ((self.family is None or self.family == family)
                and (self.vert is None or self.vert == vert)
                and (self.horiz is None or self.horiz == horiz))


@dataclass(frozen=True)
class CoachProfile:
    tags: tuple[CoachTag, ...] = ()
    source: str = ""                   # who wrote it and when, for the record
    # 0-1 multiplier on every tag. Set it to how well this coach's past reports matched what the
    # tracked data later showed (roughly their correlation). An uninformative coach at trust 1 hurts.
    trust: float = 1.0

    def adjust(self, raw: np.ndarray, mode: str) -> dict[str, np.ndarray]:
        """Per-query additive shifts to the prior for 'whiff' and 'xw'. raw = unscaled features."""
        if mode != "type":
            raise ValueError("coach priors need mode 'type' (pitch family comes from the label)")
        n = len(raw)
        dw, dx = np.zeros(n), np.zeros(n)
        types = dict(enumerate(_TYPE_ORDER))
        for k in range(n):
            t = types.get(int(round(raw[k, 2] / _TYPE_GAP)), "")
            fam = FAMILY_OF.get(t, "")
            v, h = vert_region(raw[k, 1]), horiz_region(raw[k, 0])
            for tag in self.tags:
                if tag.matches(fam, v, h):
                    w = CONF_WEIGHT[tag.confidence] * self.trust
                    dw[k] += w * tag.whiff_delta
                    dx[k] += w * tag.contact_delta
        return {"whiff": dw, "xw": dx}


# same order as shape._TYPES; duplicated to avoid a circular import
_TYPE_ORDER = ["FF", "SI", "FC", "SL", "ST", "SV", "CH", "FS", "CU", "KC", "CS", "SC", "KN", "EP", "FO"]
