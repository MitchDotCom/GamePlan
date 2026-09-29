from gameplan import Hitter, Instruction, Pitcher, generate_grid_plan
from gameplan.evaluate import ANGLE_MISMATCH_FLAG_DEG, evaluate_pitch
from gameplan.models import Action, Dev, GameContext, Pitch, Quadrant, Result, Swing

H = Hitter("h1", vba_avg=-42, baseline_cq=0.320, baseline_xwobacon=0.320)
SCALE = 1.257
# a cell where swinging is worth 0.05 wOBA more than taking, and one where it is worth 0.05 less
GO = {"swing": 0.35, "take": 0.30, "delta": 0.05, "cls": "GO"}
NOGO = {"swing": 0.20, "take": 0.25, "delta": -0.05, "cls": "NO_GO"}
CLOSE = {"swing": 0.30, "take": 0.295, "delta": 0.005, "cls": "CONDITIONAL"}
P = Pitch("1", "FF", 0.0, 3.1, 97, ivb=19.5, vaa=-4.5)


def ev(cell, action, result, **kw):
    return evaluate_pitch(cell, H, P, action, result, **kw)


def test_decision_value_is_action_taken_minus_alternative_in_runs():
    e = ev(GO, Action.SWING, Result("SWINGING_STRIKE"))
    assert abs(e.decision_value_runs - 0.05 / SCALE) < 1e-9 and e.process == "GOOD"
    e = ev(GO, Action.TAKE, Result("BALL"))
    assert abs(e.decision_value_runs + 0.05 / SCALE) < 1e-9 and e.process == "BAD"


def test_lucky_hit_on_a_no_go_pitch_is_bad_process_good_result():
    e = ev(NOGO, Action.SWING, Result("IN_PLAY", xwoba=2.0))
    assert e.process == "BAD" and e.quadrant is Quadrant.Q3_LUCKY_RESULT and e.dev is Dev.VISION_TRAINING


def test_good_take_called_strike_by_umpire_miss_is_q2_and_no_dev():
    e = ev(NOGO, Action.TAKE, Result("CALLED_STRIKE", in_zone=False))
    assert e.process == "GOOD" and e.quadrant is Quadrant.Q2_UNFORTUNATE_RESULT
    assert e.umpire_miss and e.dev is Dev.NONE


def test_no_strong_call_and_uncovered_pitches_are_not_judged():
    n = ev(CLOSE, Action.SWING, Result("FOUL"))
    assert n.process == "NEUTRAL" and n.quadrant is None and n.dev is Dev.NONE
    u = ev(None, Action.SWING, Result("FOUL"))
    assert u.process == "UNSCORED" and u.decision_value_runs is None and "no_plan_coverage" in u.flags


def test_foul_only_counts_as_good_result_with_two_strikes():
    assert ev(GO, Action.SWING, Result("FOUL"), ctx=GameContext(strikes=2)).quadrant is Quadrant.Q1_IDEAL_EXECUTION
    assert ev(GO, Action.SWING, Result("FOUL"), ctx=GameContext(strikes=0)).quadrant is Quadrant.Q2_UNFORTUNATE_RESULT


def test_execution_is_reported_from_measured_fields_not_scored():
    swing = Swing(attack_angle=-3.0, bat_speed=70, squared_up=False)        # pitch VAA -4.5 -> target +4.5, mismatch 7.5
    e = ev(GO, Action.SWING, Result("FOUL"), swing=swing)
    assert abs(e.angle_mismatch_deg - 7.5) < 1e-9 and e.squared_up is False and "angle_mismatch" not in e.flags
    big = ev(GO, Action.SWING, Result("FOUL"), swing=Swing(attack_angle=-10.0))
    assert big.angle_mismatch_deg >= ANGLE_MISMATCH_FLAG_DEG and "angle_mismatch" in big.flags
    assert ev(GO, Action.TAKE, Result("BALL"), swing=swing).angle_mismatch_deg is None     # nothing executed on a take


def test_missing_bat_tracking_is_flagged():
    assert "no_bat_tracking" in ev(GO, Action.SWING, Result("FOUL"), swing=Swing()).flags


def test_legacy_grid_plan_thresholds():
    def model(x, z, pt, ivb):
        return 0.400 if z < 2.0 else (0.240 if z > 3.2 else 0.320)
    plan = generate_grid_plan(H, Pitcher("p1"), model, ["FF"])
    assert {r.instruction for r in plan.rules} == {Instruction.GO, Instruction.NO_GO}
