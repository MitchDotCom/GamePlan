import random

from gameplan.decision import classify, p_called_strike, pitch_value, situation_weights
from gameplan.matchup import PlanMode, ReviewLabel, Situation, build_plan, review_pitch
from gameplan.models import Action, Hitter, Pitch, Result
from gameplan.savant import SwingRow
from gameplan.shape import ArsenalPitch, ContactModel, PitchRow, build_arsenal

MID = {"whiff": 0.25, "foul": 0.35, "xw": 0.36}
CHASE = {"whiff": 0.45, "foul": 0.30, "xw": 0.30}


def test_count_changes_the_call():
    d = lambda c: pitch_value(MID, p_called_strike(0.0, 2.5), *c).delta
    assert classify(d((0, 2))) == "GO"
    assert classify(d((3, 0))) == "NO_GO"     # take 3-0 with a middling hitter
    assert d((0, 2)) > d((0, 0)) > d((3, 0))


def test_far_off_pitch_is_no_go_borderline_pitch_protects_at_two_strikes():
    far = pitch_value(CHASE, p_called_strike(1.5, 2.5), 0, 2).delta
    edge = pitch_value(CHASE, p_called_strike(0.86, 2.5), 0, 2).delta
    assert far < 0 and edge > far


def test_runner_on_third_raises_the_cost_of_a_strikeout():
    base = pitch_value(CHASE, 0.0, 0, 2).delta
    rw = pitch_value(CHASE, 0.0, 0, 2, w=situation_weights(outs=1, bases=(False, False, True))).delta
    assert rw != base


def _rows(n=1500, seed=1, hero=False):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        x, z = rnd.uniform(-1.3, 1.3), rnd.uniform(1.0, 4.0)
        velo, ivb, hb, vaa = rnd.gauss(93, 3), rnd.gauss(14, 5), rnd.gauss(0, 6), rnd.gauss(-5, 1)
        low = z < 2.2
        whiff = rnd.random() < (0.08 if (hero and low) else 0.30)
        xw = None if whiff else (0.55 if (hero and low) else 0.30)
        out.append(SwingRow("h", f"2025-05-{i % 28 + 1:02d}", "FF", x, z, ivb, vaa, velo, xw, whiff,
                            x_away=x, hb=hb))
    return out


def test_hitter_model_learns_individual_zone_and_league_model_does_not():
    league = _rows(3000, 2)
    hero = _rows(600, 3, hero=True)
    m = ContactModel(hero, league, mode="shape")
    q = [[0.0, 1.6, 93, 14, 0, -5], [0.0, 3.5, 93, 14, 0, -5]]
    hit, lg = m.predict_cq(q, True), m.predict_cq(q, False)
    assert hit[0] > lg[0] + 0.05 and abs(hit[1] - lg[1]) < 0.05


def test_build_plan_snapshot_and_review():
    league, hero = _rows(3000, 2), _rows(600, 3, hero=True)
    m = ContactModel(hero, league, mode="shape")
    ars = {"FF": ArsenalPitch("FF", 1.0, 93, 14, 0, -5, 500)}
    h = Hitter("h")
    a = build_plan(m, h, "p", ars, Situation(0, 0), game_id="g1")
    b = build_plan(m, h, "p", ars, Situation(0, 2), game_id="g1", level="PA")
    assert a.plan_id != b.plan_id and a.to_dict()["cells"]
    go = [r for r in a.plan.rules if r.instruction.value == "GO"]
    assert go and min(r.zone.z_min for r in go) < 2.2
    low = Pitch("1", "FF", 0.0, 1.6, 93, ivb=14)
    r = review_pitch(a, h, low, Action.TAKE, Result("CALLED_STRIKE", in_zone=True))
    assert r.label in (ReviewLabel.DEVIATION_COST, ReviewLabel.HITTER_BEAT_MODEL, ReviewLabel.NO_COVERAGE)


def test_develop_mode_ignores_situation():
    league, hero = _rows(3000, 2), _rows(600, 3, hero=True)
    m = ContactModel(hero, league, mode="shape")
    ars = {"FF": ArsenalPitch("FF", 1.0, 93, 14, 0, -5, 500)}
    h = Hitter("h")
    a = build_plan(m, h, "p", ars, Situation(0, 2, outs=1, bases=(False, False, True)), mode=PlanMode.DEVELOP)
    b = build_plan(m, h, "p", ars, Situation(3, 0), mode=PlanMode.DEVELOP)
    assert a.cells == b.cells


def test_arsenal_by_tto_shrinks_toward_all_innings():
    rows = [PitchRow("p", "2025-05-01", "FF", 1, 95, 16, 0, -4.5) for _ in range(200)]
    rows += [PitchRow("p", "2025-05-01", "FF", 3, 92, 16, 0, -4.5) for _ in range(20)]
    rows += [PitchRow("p", "2025-05-01", "SL", 3, 85, 2, 10, -6) for _ in range(60)]
    all_t = build_arsenal(rows, "2025-07-01")
    t3 = build_arsenal(rows, "2025-07-01", tto=3)
    assert t3["FF"].velo < all_t["FF"].velo          # lower velo third time through
    assert t3["FF"].velo > 92                          # but shrunk toward the pooled mean
    assert t3["SL"].usage > all_t["SL"].usage          # more breaking balls the third time
