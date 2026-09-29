"""Registry of every fixed number the engine depends on: where it came from and how far it is verified.

status:
  VERIFIED   equals a published value (source cited; retrieved via web-search summary unless noted)
  DERIVED    fit from data by code in this repo (name the module)
  CHOICE     my setting, no source; must be tuned or justified before it is relied on
  BLUEPRINT  from the original spec, no source

Tests pin VERIFIED values and fail if code drifts from the registry."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Constant:
    value: float
    status: str
    source: str
    note: str = ""


REGISTRY: dict[str, Constant] = {
    # --- published values
    "WOBA_SCALE_2025": Constant(1.257, "VERIFIED", "FanGraphs Guts, 2025 season constants (https://www.fangraphs.com/guts.aspx?type=cn)",
                                "season-specific; update yearly. Was hard-coded 1.2 (wrong) until this registry."),
    "WBB_2025": Constant(0.693, "VERIFIED", "FanGraphs Guts 2025"),
    "WHBP_2025": Constant(0.725, "VERIFIED", "FanGraphs Guts 2025"),
    "W1B_2025": Constant(0.888, "VERIFIED", "FanGraphs Guts 2025"),
    "W2B_2025": Constant(1.265, "VERIFIED", "FanGraphs Guts 2025"),
    "W3B_2025": Constant(1.605, "VERIFIED", "FanGraphs Guts 2025"),
    "WHR_2025": Constant(2.073, "VERIFIED", "FanGraphs Guts 2025"),
    "LEAGUE_WOBA_2025": Constant(0.314, "VERIFIED", "FanGraphs Guts 2025"),
    "SQUARED_UP_BAT_COEF": Constant(1.23, "VERIFIED", "MLB Statcast glossary, squared-up rate (https://www.mlb.com/glossary/statcast/squared-up)"),
    "SQUARED_UP_PITCH_COEF": Constant(0.2116, "VERIFIED", "MLB Statcast glossary, squared-up rate"),
    "SQUARED_UP_THRESHOLD": Constant(0.80, "VERIFIED", "MLB Statcast glossary, squared-up rate"),
    "VAA_RELEASE_Y_FT": Constant(50.0, "VERIFIED", "FanGraphs VAA primer (https://blogs.fangraphs.com/a-visualized-primer-on-vertical-approach-angle-vaa/)"),
    "VAA_PLATE_FRONT_Y_FT": Constant(17.0 / 12.0, "VERIFIED", "FanGraphs VAA primer"),
    # --- choices that have not been tuned (see docs/METHODOLOGY_AUDIT.md)
    "GO_DELTA": Constant(0.020, "CHOICE", "none", "swing EV minus take EV, wOBA points"),
    "NO_GO_DELTA": Constant(-0.020, "CHOICE", "none"),
    "K_WHIFF": Constant(25.0, "CHOICE", "none", "kernel-weighted pseudo-swings; published stabilization is far larger"),
    "K_XW": Constant(12.0, "CHOICE", "none"),
    "K_SU": Constant(12.0, "CHOICE", "none"),
    "CONFIDENCE_Z": Constant(1.28, "CHOICE", "none", "one-sided 90% bound: a call requires swing-minus-take to stay on its side of zero"),
    "XWOBA_CONTACT_SD": Constant(0.377, "DERIVED", "SD of Savant xwOBA on 123,890 non-bunt balls in play, all 2025 regular-season pitches (data/league)"),
    "K_GLOBAL_WHIFF": Constant(150.0, "DERIVED", "docs/study_hier.txt: hitter-level term, k_global in {50,150,400} at N=50..400; 150 is within the best interval at every N; published stabilization for contact% is about 100 PA (about 250 swings)",
                               "swings"),
    "K_GLOBAL_XW": Constant(60.0, "DERIVED", "docs/study_hier.txt (k_global 150 x 0.4 balls-in-play per swing)", "balls in play"),
    "SITUATION_SHRINK_N": Constant(100.0, "CHOICE", "none"),
    "MIN_LEVERAGE": Constant(0.04, "CHOICE", "none"),
    # --- blueprint numbers with no support
    "BLUEPRINT_ANGLE_PENALTY": Constant(4.0, "BLUEPRINT", "original spec"),
    "BLUEPRINT_TIMING_PENALTY": Constant(2.5, "BLUEPRINT", "original spec"),
    "BLUEPRINT_VELO_TRIGGER_MPH": Constant(2.5, "BLUEPRINT", "original spec"),
    "BLUEPRINT_INCHES_PER_MPH": Constant(1.0, "BLUEPRINT", "original spec"),
}


def value(name: str) -> float:
    return REGISTRY[name].value


def by_status(status: str) -> dict[str, Constant]:
    return {k: v for k, v in REGISTRY.items() if v.status == status}
