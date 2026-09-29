from gameplan import (
    Action, Dev, GameContext, Hitter, Instruction, Pitch, Pitcher, Plan, Quadrant, Result,
    Rule, Swing, Zone, adjust_plan, evaluate_pitch, generate_grid_plan,
)

H = Hitter("h1", vba_avg=-42, baseline_xwoba=0.320)
HIGH_HEAT = Rule("hi_fb", Instruction.NO_GO, Zone(-0.9, 0.9, 2.8, 4.0), frozenset({"FF"}), min_ivb=18)
PLAN = Plan("h1", "p1", (HIGH_HEAT,))


def ev(pitch, action, result, ctx=GameContext(), swing=None, plan=PLAN):
    return evaluate_pitch(plan, H, pitch, action, result, ctx, swing)


def test_lucky_bloop_on_no_go_is_bad_decision():
    p = Pitch("1", "FF", 0.0, 3.1, 97, ivb=19.5, vaa=-4.5)
    e = ev(p, Action.SWING, Result("IN_PLAY", xwoba=0.210 + 0.2), swing=Swing(9, 12))
    assert e.decision_score == 0 and e.quadrant is Quadrant.Q3_LUCKY_RESULT
    assert e.dev in (Dev.VISION_TRAINING, Dev.BOTH)


def test_hr_on_no_go_still_bad_decision():
    p = Pitch("1", "FF", 0.0, 3.1, 97, ivb=19.5)
    e = ev(p, Action.SWING, Result("IN_PLAY", xwoba=2.0), swing=Swing(None, 0))
    assert e.decision_score == 0 and e.quadrant is Quadrant.Q3_LUCKY_RESULT


def test_umpire_miss_on_taken_no_go_is_q2_no_dev():
    p = Pitch("2", "FF", 1.1, 3.4, 96, ivb=19)
    plan = Plan("h1", "p1", (Rule("r", Instruction.NO_GO, Zone(0.8, 2, 1, 4)),))
    e = ev(p, Action.TAKE, Result("CALLED_STRIKE", in_zone=False), plan=plan)
    assert (e.decision_score, e.quadrant, e.dev) == (100, Quadrant.Q2_UNFORTUNATE_RESULT, Dev.NONE)
    assert e.umpire_miss and e.execution_score is None


def test_take_has_no_execution_score():
    p = Pitch("3", "SL", 0, 2, 85)
    assert ev(p, Action.TAKE, Result("BALL")).execution_score is None


def test_execution_penalizes_angle_and_timing():
    p = Pitch("4", "SL", 0, 2, 85, vaa=-6)
    good = ev(p, Action.SWING, Result("FOUL"), swing=Swing(6, 0)).execution_score
    bad = ev(p, Action.SWING, Result("FOUL"), swing=Swing(0, 12)).execution_score
    assert good == 100 and bad < 60


def test_good_decision_bad_execution_gets_mechanical_work():
    go = Plan("h1", "p1", (Rule("g", Instruction.GO, Zone(-1, 1, 1, 4)),))
    p = Pitch("5", "FF", 0, 2.5, 93, vaa=-5)
    e = ev(p, Action.SWING, Result("SWINGING_STRIKE"), swing=Swing(-3, 15), plan=go)
    assert e.decision_score == 100 and e.dev is Dev.MECHANICAL_WORK
    assert e.quadrant is Quadrant.Q2_UNFORTUNATE_RESULT


def test_two_strike_protect_flips_borderline_no_go():
    plan = Plan("h1", "p1", (Rule("r", Instruction.NO_GO, Zone(-2, 2, 0, 5)),))
    edge = Pitch("6", "FF", 0.9, 2.5, 94)  # ~0.9 in off the plate edge
    far = Pitch("7", "FF", 1.5, 2.5, 94)
    ctx = GameContext(strikes=2)
    assert ev(edge, Action.SWING, Result("FOUL"), ctx, plan=plan).decision_score == 100
    assert ev(far, Action.SWING, Result("FOUL"), ctx, plan=plan).instruction is Instruction.NO_GO
    assert ev(far, Action.SWING, Result("FOUL"), ctx, plan=plan).decision_score == 0


def test_no_go_beats_go_on_overlap():
    plan = Plan("h1", "p1", (
        Rule("g", Instruction.GO, Zone(-1, 1, 1, 4)),
        Rule("n", Instruction.NO_GO, Zone(-1, 1, 1, 4)),
    ))
    assert ev(Pitch("8", "FF", 0, 2, 94), Action.TAKE, Result("BALL"), plan=plan).instruction is Instruction.NO_GO


def test_velocity_drop_extends_fastball_go_zone_only():
    plan = Plan("h1", "p1", (
        Rule("fb", Instruction.GO, Zone(-1, 1, 2, 3), frozenset({"FF"})),
        Rule("sl", Instruction.GO, Zone(-1, 1, 2, 3), frozenset({"SL"})),
        Rule("no", Instruction.NO_GO, Zone(-1, 1, 3, 4), frozenset({"FF"})),
    ))
    assert adjust_plan(plan, 95, 93.0) is plan  # 2.0 mph: below trigger
    adj = adjust_plan(plan, 95, 92.0)
    fb, sl, no = adj.rules
    assert abs(fb.zone.z_min - (2 - 3 / 12)) < 1e-9
    assert sl.zone.z_min == 2 and no.zone.z_min == 3
    assert adjust_plan(plan, 95, 80).rules[0].zone.z_min == 2 - 4 / 12  # capped


def test_grid_plan_thresholds():
    def model(x, z, pt, ivb):
        return 0.400 if z < 2.0 else (0.280 if z > 3.2 else 0.320)
    plan = generate_grid_plan(H, Pitcher("p1"), model, ["FF"])
    kinds = {r.instruction for r in plan.rules}
    assert kinds == {Instruction.GO, Instruction.NO_GO}
    assert all(r.zone.z_max <= 2.01 for r in plan.rules if r.instruction is Instruction.GO)
