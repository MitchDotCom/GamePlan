"""Pitch evaluation on three separate axes: decision, execution, result.

All scoring is deterministic code. Constants below are starting points to calibrate, not facts."""
from __future__ import annotations

from .models import (
    Action, Dev, Evaluation, GameContext, Hitter, Instruction, Pitch, Plan, Quadrant,
    Result, Rule, Swing,
)

# Decision scores for (instruction, action)
SCORE_GO_SWING = 100
SCORE_GO_TAKE = 25
SCORE_NO_GO_TAKE = 100
SCORE_NO_GO_SWING = 0
SCORE_CONDITIONAL_NEUTRAL = 60         # no call in a non-protect count
PROTECT_SWING, PROTECT_TAKE = 100, 40  # borderline pitch, 2 strikes
GOOD_DECISION = 75

# Execution: penalty per degree of attack-angle error and per ms of timing error
ANGLE_PENALTY = 4.0
TIMING_PENALTY = 2.5
GOOD_EXECUTION = 60

PROTECT_TOLERANCE_FT = 2.5 / 12.0      # NO_GO pitches this close to the called zone flip to protect at 2 strikes


def _select_rule(plan: Plan, pitch: Pitch, strikes: int) -> Rule | None:
    order = {Instruction.NO_GO: 2, Instruction.CONDITIONAL: 1, Instruction.GO: 0}
    hits = [r for r in plan.rules if r.applies(pitch, strikes)]
    if not hits:
        return None
    return max(hits, key=lambda r: (r.priority, order[r.instruction]))


def resolve(plan: Plan, pitch: Pitch, ctx: GameContext) -> tuple[Instruction, Rule | None, bool]:
    """Returns (instruction, matched rule, protect_mode)."""
    rule = _select_rule(plan, pitch, ctx.strikes)
    ins = rule.instruction if rule else plan.default
    protect = False
    if ctx.strikes == 2:
        near = ctx.strike_zone.distance_to(pitch.x, pitch.z) <= PROTECT_TOLERANCE_FT
        if ins is Instruction.CONDITIONAL or (ins is Instruction.NO_GO and near):
            protect = True
            ins = Instruction.CONDITIONAL
    return ins, rule, protect


def decision_score(ins: Instruction, action: Action, protect: bool) -> int:
    if ins is Instruction.GO:
        return SCORE_GO_SWING if action is Action.SWING else SCORE_GO_TAKE
    if ins is Instruction.NO_GO:
        return SCORE_NO_GO_SWING if action is Action.SWING else SCORE_NO_GO_TAKE
    if protect:
        return PROTECT_SWING if action is Action.SWING else PROTECT_TAKE
    return SCORE_CONDITIONAL_NEUTRAL


def execution_score(pitch: Pitch, swing: Swing | None) -> tuple[int | None, str | None]:
    """Attack angle vs the pitch's plane, plus timing. None when there is nothing to score."""
    if swing is None:
        return None, None
    parts, err = [], 0.0
    if swing.vaa_swing is not None and pitch.vaa is not None:
        err += ANGLE_PENALTY * abs(swing.vaa_swing - (-pitch.vaa))
        parts.append("angle")
    if swing.timing_error_ms is not None:
        err += TIMING_PENALTY * abs(swing.timing_error_ms)
        parts.append("timing")
    if not parts:
        return None, "no_bat_tracking"
    flag = None if len(parts) == 2 else f"partial_execution:{parts[0]}_only"
    return max(0, round(100 - err)), flag


def _result_good(result: Result, hitter: Hitter, strikes: int) -> bool:
    c = result.call.upper()
    if c in {"BALL", "HBP", "WALK"}:
        return True
    if c == "IN_PLAY":
        return result.xwoba is not None and result.xwoba >= hitter.baseline_xwobacon
    if c == "FOUL":
        return strikes == 2   # a foul only helps when it keeps the at-bat alive
    return False              # CALLED_STRIKE, SWINGING_STRIKE, unknown


def _quadrant(dec: int, good_result: bool) -> Quadrant:
    good_process = dec >= GOOD_DECISION
    if good_process:
        return Quadrant.Q1_IDEAL_EXECUTION if good_result else Quadrant.Q2_UNFORTUNATE_RESULT
    return Quadrant.Q3_LUCKY_RESULT if good_result else Quadrant.Q4_PROCESS_FAILURE


def _dev(dec: int, exe: int | None, ump_miss: bool) -> Dev:
    if ump_miss:
        return Dev.NONE
    bad_dec = dec < GOOD_DECISION
    bad_exe = exe is not None and exe < GOOD_EXECUTION
    if bad_dec and bad_exe:
        return Dev.BOTH
    if bad_dec:
        return Dev.VISION_TRAINING
    if bad_exe:
        return Dev.MECHANICAL_WORK
    return Dev.NONE


def evaluate_pitch(
    plan: Plan,
    hitter: Hitter,
    pitch: Pitch,
    action: Action,
    result: Result,
    ctx: GameContext = GameContext(),
    swing: Swing | None = None,
) -> Evaluation:
    ins, rule, protect = resolve(plan, pitch, ctx)
    dec = decision_score(ins, action, protect)
    exe, exe_flag = execution_score(pitch, swing if action is Action.SWING else None)
    good = _result_good(result, hitter, ctx.strikes)
    quad = _quadrant(dec, good)

    call = result.call.upper()
    ump_miss = (
        action is Action.TAKE and call == "CALLED_STRIKE" and result.in_zone is False
    ) or (
        action is Action.TAKE and call == "BALL" and result.in_zone is True
    )
    flags: list[str] = []
    if exe_flag:
        flags.append(exe_flag)
    if ins is Instruction.CONDITIONAL and not protect:
        flags.append("no_plan_coverage" if rule is None else "conditional_neutral")
    if protect:
        flags.append("protect_mode")
    if ump_miss:
        flags.append("umpire_miss")
    if action is Action.SWING and exe is None and "no_bat_tracking" not in flags:
        flags.append("no_bat_tracking")

    label = "PROTECT" if protect else ins.value
    verb = "swung" if action is Action.SWING else "took"
    rationale = (
        f"{label} pitch, hitter {verb}: decision {dec}"
        + (f", execution {exe}" if exe is not None else "")
        + f". Result {'good' if good else 'bad'} ({call})"
        + (", umpire miss" if ump_miss else "")
        + "."
    )
    return Evaluation(
        pitch_id=pitch.pitch_id,
        instruction=ins,
        rule_id=rule.rule_id if rule else None,
        decision_score=dec,
        execution_score=exe,
        quadrant=quad,
        dev=_dev(dec, exe, ump_miss),
        umpire_miss=ump_miss,
        rationale=rationale,
        flags=tuple(flags),
    )
