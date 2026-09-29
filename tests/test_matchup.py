import random

from gameplan.decision import DEFAULT
from gameplan.decision import (
    SituationConfig, SituationPolicy, apply_situation, classify, p_called_strike, pitch_value, situation_weights,
)
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


def test_runner_on_third_makes_strikeouts_costlier_and_contact_worth_more():
    r3 = (False, False, True)
    w = situation_weights(outs=1, bases=r3)
    assert w.d_k < 0 and w.d_bip > 0
    base = pitch_value(MID, 0.0, 0, 2).delta
    assert pitch_value(MID, 0.0, 0, 2, apply_situation(DEFAULT, w)).delta != base


def test_policy_scales_the_adjustment_and_contact_first_caps_whiff():
    r3 = (False, False, True)
    off = situation_weights(1, r3, config=SituationConfig(runner_third_lt2=SituationPolicy.OFF, score_inning=SituationPolicy.OFF))
    mild = situation_weights(1, r3, config=SituationConfig(runner_third_lt2=SituationPolicy.MILD, score_inning=SituationPolicy.OFF))
    strong = situation_weights(1, r3, config=SituationConfig(runner_third_lt2=SituationPolicy.STRONG, score_inning=SituationPolicy.OFF))
    cf = situation_weights(1, r3, config=SituationConfig(runner_third_lt2=SituationPolicy.CONTACT_FIRST, score_inning=SituationPolicy.OFF))
    assert off.d_k == 0 and abs(strong.d_k) > abs(mild.d_k) > 0
    assert abs(strong.d_k - 2 * mild.d_k) < 1e-9
    assert cf.max_whiff is not None and strong.max_whiff is None


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
    assert hit[0] > lg[0] + 0.05 and hit[0] > hit[1]       # better than league low, and better low than high (the data says so)


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


def test_contact_first_demotes_high_whiff_go_cells():
    from gameplan.decision import SituationConfig, SituationPolicy
    league, hero = _rows(3000, 2), _rows(600, 3, hero=True)
    m = ContactModel(hero, league, mode="shape")
    ars = {"FF": ArsenalPitch("FF", 1.0, 93, 14, 0, -5, 500)}
    h = Hitter("h")
    sit = Situation(0, 0, outs=1, bases=(False, False, True))
    strong = build_plan(m, h, "p", ars, sit, config=SituationConfig(runner_third_lt2=SituationPolicy.STRONG, score_inning=SituationPolicy.OFF))
    cf = build_plan(m, h, "p", ars, sit,
                    config=SituationConfig(runner_third_lt2=SituationPolicy.CONTACT_FIRST,
                                           contact_first_max_whiff=0.15))
    go = lambda snap: sum(1 for c in snap.cells.values() if c["cls"] == "GO")
    assert go(cf) < go(strong)


def test_research_flags_and_pitcher_state_are_recorded():
    from gameplan.shape import PitcherState
    league, hero = _rows(3000, 2), _rows(600, 3, hero=True)
    m = ContactModel(hero, league, mode="shape")
    ars = {"FF": ArsenalPitch("FF", 1.0, 93, 14, 0, -5, 500)}
    h = Hitter("h")
    st = PitcherState(tto=3, pitch_count=88, fb_drift=-1.2)
    snap = build_plan(m, h, "p", ars, Situation(tto=3), pitcher_state=st, apply_tto_effect=True)
    assert any("pitcher state" in n for n in snap.notes)
    a = build_plan(m, h, "p", ars, Situation(tto=3), pitcher_state=st, apply_tto_effect=False)
    assert a.plan_id != snap.plan_id
    hard_out = Result("IN_PLAY", xwoba=0.9, is_hit=False)
    r = review_pitch(snap, h, Pitch("1", "FF", 0.0, 1.6, 93, ivb=14), Action.SWING, hard_out)
    assert isinstance(r.research_flags, tuple)


def test_recommend_policy_tracks_strikeout_exposure():
    from gameplan.decision import SituationPolicy
    from gameplan.matchup import matchup_k_risk, recommend_policy
    ars = {"FF": ArsenalPitch("FF", 1.0, 93, 14, 0, -5, 500)}
    league = _rows(3000, 2)
    contact = ContactModel([], league, mode="shape")                       # league-average hitter, whiff .30
    swing_miss = ContactModel(_rows(800, 5, hero=False), league, mode="shape")
    assert matchup_k_risk(contact, ars, use_hitter=False) > 0.2
    pol, k, why = recommend_policy(swing_miss, ars)
    assert pol in (SituationPolicy.CONTACT_FIRST, SituationPolicy.STRONG) and "whiff" in why


def test_score_inning_walk_is_worth_less_when_late_close_and_ignored_in_blowouts():
    from gameplan.decision import SituationConfig, SituationPolicy, situation_weights
    cfg = SituationConfig(runner_third_lt2=SituationPolicy.OFF, score_inning=SituationPolicy.STRONG)
    late_close = situation_weights(1, (False, False, False), score_diff=0, inning=9, config=cfg)
    blowout = situation_weights(1, (False, False, False), score_diff=-6, inning=9, config=cfg)
    off = situation_weights(1, (False, False, False), score_diff=0, inning=9,
                            config=SituationConfig(score_inning=SituationPolicy.OFF, other_states=SituationPolicy.OFF))
    assert late_close.d_bb < 0 and blowout.d_bb == 0 and off.d_bb == 0


def test_policy_book_layers_and_explains():
    from gameplan.decision import PolicyBook, SituationConfig, SituationOverride, SituationPolicy as P
    book = PolicyBook(
        default=SituationConfig(runner_third_lt2=P.MILD),
        by_starter={"S1": SituationOverride(runner_third_lt2=P.CONTACT_FIRST, risp_two_outs=P.STRONG)},
        by_hitter={"H1": SituationOverride(runner_third_lt2=P.STRONG)},
        by_pair={"H1|S1": SituationOverride(risp_two_outs=P.OFF)},
    )
    cfg = book.resolve("H1", "S1")
    assert cfg.runner_third_lt2 is P.STRONG and cfg.risp_two_outs is P.OFF        # hitter beats starter, pair beats both
    assert book.resolve("H2", "S1").runner_third_lt2 is P.CONTACT_FIRST           # starter alone
    assert book.resolve("H2", "S2") == book.default
    why = book.explain("H1", "S1")
    assert why["runner_third_lt2"] == "hitter" and why["risp_two_outs"] == "pair" and why["score_inning"] == "default"
    assert PolicyBook.from_json(book.to_json()).resolve("H1", "S1") == cfg
    flipped = PolicyBook(book.default, book.by_starter, book.by_hitter, book.by_pair, ("hitter", "starter", "pair"))
    assert flipped.resolve("H1", "S1").runner_third_lt2 is P.CONTACT_FIRST        # precedence is configurable


def test_vectorised_and_plan_standard_errors_agree_and_thin_evidence_withholds_calls():
    import numpy as np
    from gameplan.decision import DEFAULT, swing_se_np
    from gameplan.matchup import _swing_se
    league, hero = _rows(3000, 2), _rows(600, 3, hero=True)
    m = ContactModel(hero, league, mode="shape")
    p = {"whiff": 0.25, "foul": 0.35, "xw": 0.36}
    a = _swing_se(p, DEFAULT, Situation(1, 1), 12.0, 5.0, m)
    b = float(swing_se_np(np.array([.25]), np.array([.35]), np.array([.36]), [1], [1], np.array([12.0]), np.array([5.0]),
                          m.k["whiff"], m.k["xw"])[0])
    assert abs(a - b) < 1e-12
    thin = ContactModel(_rows(15, 4, hero=True), league, mode="shape")
    ars = {"FF": ArsenalPitch("FF", 1.0, 93, 14, 0, -5, 500)}
    h = Hitter("h")
    loose = build_plan(thin, h, "p", ars, Situation(0, 0), z_conf=0.0)
    firm = build_plan(thin, h, "p", ars, Situation(0, 0), z_conf=1.28)
    calls = lambda snap: sum(1 for c in snap.cells.values() if c["cls"] != "CONDITIONAL")
    assert calls(firm) <= calls(loose) and any(c["low_support"] for c in firm.cells.values()) or calls(firm) == calls(loose)
