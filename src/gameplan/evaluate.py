"""Pitch evaluation: decision value, measured execution diagnostics, and result, kept separate.

Decision value is the published-style measure (Savant swing/take, TJStats batter decision value): the
model's expected value of the action the hitter took minus the alternative, at the count and situation
of the plan snapshot. Units are runs. There are no invented 0-100 scores.

Execution is not scored. Only measured Statcast fields are reported (attack angle, bat speed, squared-up)
plus the angle mismatch |attack angle - (-pitch VAA)|. Across 58k balls in play in 2025 the mismatch is
weakly related to squared-up rate (top-quintile mismatch of 11 degrees or more: 61.8% squared up vs 69%
for the best two quintiles; r = -0.06) and to whiffs (r = +0.20), so it is a flag, not a score."""
from __future__ import annotations

from typing import Optional

from .constants import value as _const
from .models import Action, Dev, Evaluation, GameContext, Hitter, Instruction, Pitch, Quadrant, Result, Swing

DECISION_THRESHOLD = _const("GO_DELTA")      # |swing EV - take EV| under this is "no strong call"
ANGLE_MISMATCH_FLAG_DEG = 11.1               # top quintile of 2025 balls in play (DERIVED, see docstring)


def _result_good(result: Result, hitter: Hitter, strikes: int) -> bool:
    c = result.call.upper()
    if c in {"BALL", "HBP", "WALK"}:
        return True
    if c == "IN_PLAY":
        return result.xwoba is not None and result.xwoba >= hitter.baseline_xwobacon
    if c == "FOUL":
        return strikes == 2   # a foul only helps when it keeps the at-bat alive
    return False              # CALLED_STRIKE, SWINGING_STRIKE, FOUL_TIP, unknown


def evaluate_pitch(
    cell: Optional[dict],
    hitter: Hitter,
    pitch: Pitch,
    action: Action,
    result: Result,
    ctx: GameContext = GameContext(),
    swing: Optional[Swing] = None,
    cell_key: Optional[str] = None,
    scale: Optional[float] = None,
    threshold: float = DECISION_THRESHOLD,
) -> Evaluation:
    """cell: one plan-snapshot cell {"swing": EV, "take": EV, "delta": swing-take, "cls": call}, or None
    if the plan did not cover the pitch. EVs are on the wOBA scale; scale converts to runs."""
    scale = scale or _const("WOBA_SCALE_2025")
    call = result.call.upper()
    ump_miss = (action is Action.TAKE and call == "CALLED_STRIKE" and result.in_zone is False) or \
               (action is Action.TAKE and call == "BALL" and result.in_zone is True)
    flags: list[str] = []

    if cell is None:
        dv_runs, process, instruction = None, "UNSCORED", Instruction.CONDITIONAL
        flags.append("no_plan_coverage")
    else:
        dv = cell["delta"] if action is Action.SWING else -cell["delta"]
        dv_runs = dv / scale
        process = "GOOD" if dv >= threshold else "BAD" if dv <= -threshold else "NEUTRAL"
        instruction = Instruction(cell["cls"])
        if process == "NEUTRAL":
            flags.append("no_strong_call")

    good = _result_good(result, hitter, ctx.strikes)
    if process == "GOOD":
        quad = Quadrant.Q1_IDEAL_EXECUTION if good else Quadrant.Q2_UNFORTUNATE_RESULT
    elif process == "BAD":
        quad = Quadrant.Q3_LUCKY_RESULT if good else Quadrant.Q4_PROCESS_FAILURE
    else:
        quad = None

    mismatch = None
    su = None
    if action is Action.SWING and swing is not None:
        su = swing.squared_up
        if swing.attack_angle is not None and pitch.vaa is not None:
            mismatch = abs(swing.attack_angle - (-pitch.vaa))
            if mismatch >= ANGLE_MISMATCH_FLAG_DEG:
                flags.append("angle_mismatch")
        elif swing.attack_angle is None:
            flags.append("no_bat_tracking")
    if ump_miss:
        flags.append("umpire_miss")

    # Development flags only from decisions the model was confident about, never from one pitch's
    # execution. Angle mismatch is recorded for aggregation, not assigned here.
    dev = Dev.NONE if (ump_miss or process != "BAD") else Dev.VISION_TRAINING

    verb = "swung" if action is Action.SWING else "took"
    rationale = (f"{instruction.value} cell, hitter {verb}: "
                 + (f"decision value {dv_runs:+.3f} runs ({process})" if dv_runs is not None else "plan silent")
                 + f". Result {'good' if good else 'bad'} ({call})" + (", umpire miss" if ump_miss else "") + ".")
    return Evaluation(
        pitch_id=pitch.pitch_id, instruction=instruction, rule_id=cell_key, decision_value_runs=dv_runs,
        process=process, quadrant=quad, dev=dev, umpire_miss=ump_miss, rationale=rationale,
        flags=tuple(flags), angle_mismatch_deg=mismatch, squared_up=su,
    )
