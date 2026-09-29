"""What a park / tracking system can supply, and which model tier that supports.

Low-A and High-A parks differ: some have TrackMan, some Hawk-Eye, some little or nothing, and the
systems do not measure identically. This module does not assert vendor specifics. It records, per
park, which fields are available so the pipeline can pick a tier, and holds per-system offsets that
must be estimated (for example against Savant, or from parks where two systems overlap) before data
from different systems is pooled."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Tier(str, Enum):
    FULL = "FULL"              # location, velo, IVB/HB/VAA, exit velo + launch angle, bat tracking
    SHAPE = "SHAPE"           # location, full pitch shape, exit velo + launch angle
    BASIC = "BASIC"           # location, pitch type, velo, outcome only
    REPORTS_ONLY = "REPORTS_ONLY"   # coach reports plus whatever counting stats exist


@dataclass(frozen=True)
class DataProfile:
    park: str
    system: str = "unknown"             # e.g. "TrackMan", "Hawk-Eye", "none": whatever the org records
    has_location: bool = False
    has_velo: bool = False
    has_pitch_shape: bool = False       # IVB / HB / VAA or the raw release kinematics
    has_batted_ball: bool = False       # exit velocity and launch angle
    has_bat_tracking: bool = False
    has_pitcher_state: bool = False     # pitch count, TTO derivable from the feed
    # Additive corrections onto the Savant-like scale, to be estimated per system.
    offsets: dict = field(default_factory=dict)   # e.g. {"plate_z_ft": 0.0, "ivb_in": 0.0, "hb_in": 0.0}

    def tier(self) -> Tier:
        if not (self.has_location and self.has_velo):
            return Tier.REPORTS_ONLY
        if not self.has_pitch_shape or not self.has_batted_ball:
            return Tier.BASIC
        return Tier.FULL if self.has_bat_tracking else Tier.SHAPE

    def model_settings(self) -> dict:
        """Constructor arguments for ContactModel that this data supports."""
        t = self.tier()
        if t in (Tier.FULL, Tier.SHAPE):
            return {"mode": "shape", "xw_attr": "xwoba"}
        if t is Tier.BASIC:
            return {"mode": "typevelo" if self.has_velo else "type",
                    "xw_attr": "xwoba" if self.has_batted_ball else "woba"}
        return {}


def load_profiles(text: str) -> dict[str, DataProfile]:
    """JSON: {"Visalia": {"system": "...", "has_location": true, ...}, ...}"""
    return {park: DataProfile(park=park, **d) for park, d in json.loads(text).items()}


def dump_profiles(profiles: dict[str, DataProfile]) -> str:
    return json.dumps({k: {f: v for f, v in asdict(p).items() if f != "park"} for k, p in profiles.items()},
                      indent=1)
