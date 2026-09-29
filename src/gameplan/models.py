"""Data model. Units: feet for plate coordinates (x: catcher's view, + = toward 1B side;
z: height off ground), degrees for angles, mph for velocity, ms for time, inches for break."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


class Action(str, Enum):
    SWING = "SWING"
    TAKE = "TAKE"


class Instruction(str, Enum):
    GO = "GO"
    NO_GO = "NO_GO"
    CONDITIONAL = "CONDITIONAL"


class Quadrant(str, Enum):
    Q1_IDEAL_EXECUTION = "Q1_IDEAL_EXECUTION"        # good process, good result
    Q2_UNFORTUNATE_RESULT = "Q2_UNFORTUNATE_RESULT"  # good process, bad result
    Q3_LUCKY_RESULT = "Q3_LUCKY_RESULT"              # bad process, good result
    Q4_PROCESS_FAILURE = "Q4_PROCESS_FAILURE"        # bad process, bad result


class Dev(str, Enum):
    NONE = "NONE"
    VISION_TRAINING = "VR_VISION_TRAINING"
    MECHANICAL_WORK = "MECHANICAL_CAGE_WORK"
    BOTH = "VISION_AND_MECHANICAL"


@dataclass(frozen=True)
class Hitter:
    player_id: str
    name: str = ""
    vba_avg: float = -35.0          # vertical bat angle at contact
    vaa_swing: float = 12.0         # attack angle
    ttc_ms: int = 155               # swing time to contact
    bat_speed_90: float = 72.0
    # Two baselines on purpose, they are different scales:
    #   baseline_cq: whiff-adjusted contact quality per swing, (1 - whiff rate) * xwOBAcon.
    #                Used by the plan generator to set GO / NO_GO thresholds.
    #   baseline_xwobacon: mean xwOBA on balls in play. Used by the evaluator to judge a batted ball.
    baseline_cq: float = 0.250
    baseline_xwobacon: float = 0.350


@dataclass(frozen=True)
class Pitcher:
    player_id: str
    name: str = ""
    fb_velo: float = 94.0
    fb_ivb: float = 16.0


@dataclass(frozen=True)
class Zone:
    x_min: float
    x_max: float
    z_min: float
    z_max: float

    def contains(self, x: float, z: float) -> bool:
        return self.x_min <= x <= self.x_max and self.z_min <= z <= self.z_max

    def distance_to(self, x: float, z: float) -> float:
        """Feet outside the box (0 inside). Euclidean to nearest edge/corner."""
        dx = max(self.x_min - x, 0.0, x - self.x_max)
        dz = max(self.z_min - z, 0.0, z - self.z_max)
        return (dx * dx + dz * dz) ** 0.5

    def shifted_down(self, inches: float) -> "Zone":
        return replace(self, z_min=self.z_min - inches / 12.0)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    instruction: Instruction
    zone: Zone
    pitch_types: Optional[frozenset[str]] = None   # None = any
    min_ivb: Optional[float] = None                # rule applies only if pitch IVB >= this
    strikes: Optional[frozenset[int]] = None       # None = any strike count
    priority: int = 0                              # higher wins; ties -> NO_GO wins

    def applies(self, pitch: "Pitch", strikes: int) -> bool:
        if not self.zone.contains(pitch.x, pitch.z):
            return False
        if self.pitch_types is not None and pitch.pitch_type not in self.pitch_types:
            return False
        if self.min_ivb is not None and (pitch.ivb is None or pitch.ivb < self.min_ivb):
            return False
        if self.strikes is not None and strikes not in self.strikes:
            return False
        return True


@dataclass(frozen=True)
class Plan:
    hitter_id: str
    pitcher_id: str
    rules: tuple[Rule, ...]
    default: Instruction = Instruction.CONDITIONAL   # anything no rule covers
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GameContext:
    balls: int = 0
    strikes: int = 0
    # The zone the umpire is actually calling (feet). Override for a low/wide zone.
    strike_zone: Zone = Zone(-0.83, 0.83, 1.5, 3.5)


@dataclass(frozen=True)
class Pitch:
    pitch_id: str
    pitch_type: str
    x: float
    z: float
    velo: float
    ivb: Optional[float] = None
    vaa: Optional[float] = None   # pitch approach angle (negative = descending)


@dataclass(frozen=True)
class Swing:
    """Only present when the hitter swung. Bat-tracking fields may be missing."""
    vaa_swing: Optional[float] = None     # attack angle of this swing
    timing_error_ms: Optional[float] = None   # + late, - early


@dataclass(frozen=True)
class Result:
    call: str                        # e.g. BALL, CALLED_STRIKE, SWINGING_STRIKE, FOUL, IN_PLAY
    xwoba: Optional[float] = None    # batted balls only
    ev: Optional[float] = None
    la: Optional[float] = None
    in_zone: Optional[bool] = None   # true rulebook location, used to spot umpire misses
    is_hit: Optional[bool] = None    # for balls in play: did it fall for a hit (vs an out)


@dataclass(frozen=True)
class Evaluation:
    pitch_id: str
    instruction: Instruction           # after count resolution
    rule_id: Optional[str]
    decision_score: int
    execution_score: Optional[int]     # None on a take: nothing to execute
    quadrant: Quadrant
    dev: Dev
    umpire_miss: bool
    rationale: str
    flags: tuple[str, ...] = field(default_factory=tuple)
