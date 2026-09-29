import numpy as np

from gameplan.baseout import fit, outcome_class, state_key
from gameplan.coach import CoachProfile, CoachTag, horiz_region, vert_region
from gameplan.profiles import DataProfile, Tier, dump_profiles, load_profiles
from gameplan.shape import ContactModel, PitchRow, PitcherState, ArsenalBasis, arsenal_for_state, _type_code
from gameplan.savant import SwingRow
import random


def test_coach_tag_shifts_only_the_matching_family_and_height():
    prof = CoachProfile((CoachTag(family="FB", vert="HIGH", whiff_delta=0.10, contact_delta=-0.05, confidence=3),))
    ff_high = [0.0, 3.2, _type_code("FF")]
    ff_low = [0.0, 1.8, _type_code("FF")]
    sl_high = [0.0, 3.2, _type_code("SL")]
    adj = prof.adjust(np.array([ff_high, ff_low, sl_high]), "type")
    assert list(adj["whiff"]) == [0.10, 0.0, 0.0] and list(adj["xw"]) == [-0.05, 0.0, 0.0]


def test_trust_scales_the_coach_prior():
    tag = CoachTag(family="FB", whiff_delta=0.10, confidence=3)
    q = np.array([[0.0, 2.5, _type_code("FF")]])
    assert abs(CoachProfile((tag,), trust=0.5).adjust(q, "type")["whiff"][0] - 0.05) < 1e-9


def _swings(n, seed, whiff_p):
    rnd = random.Random(seed)
    return [SwingRow("h", "2025-05-01", "FF", rnd.uniform(-1, 1), rnd.uniform(1.5, 3.5), 14, -5, 93,
                     None if (w := rnd.random() < whiff_p) else 0.32, w, x_away=0.0, hb=0.0)
            for _ in range(n)]


def test_coach_prior_matters_early_and_fades_with_data():
    league = _swings(4000, 1, 0.25)
    coach = CoachProfile((CoachTag(family="FB", whiff_delta=0.20, confidence=3),))
    q = [[0.0, 2.5, _type_code("FF")]]
    few = ContactModel(_swings(10, 2, 0.25), league, mode="type")
    many = ContactModel(_swings(800, 2, 0.25), league, mode="type")
    d_few = few.predict(q, coach=coach)["whiff"][0] - few.predict(q)["whiff"][0]
    d_many = many.predict(q, coach=coach)["whiff"][0] - many.predict(q)["whiff"][0]
    assert d_few > 0.10 and d_many < d_few / 3


def test_loc_and_woba_modes_run():
    league, hero = _swings(2000, 1, 0.25), _swings(300, 2, 0.30)
    for mode in ("loc", "type", "typevelo", "shape"):
        m = ContactModel(hero, league, mode=mode)
        Q, mask = m.query_swings(hero)
        assert len(m.predict_pair(Q)[1]["whiff"]) == mask.sum()


def test_profile_tier_and_model_settings():
    full = DataProfile("A", "Hawk-Eye", True, True, True, True, True, True)
    shape = DataProfile("B", "TrackMan", True, True, True, True, False, True)
    basic = DataProfile("C", "unknown", True, True, False, False, False, False)
    none = DataProfile("D")
    assert (full.tier(), shape.tier(), basic.tier(), none.tier()) == (Tier.FULL, Tier.SHAPE, Tier.BASIC, Tier.REPORTS_ONLY)
    assert basic.model_settings() == {"mode": "typevelo", "xw_attr": "woba"}
    assert none.model_settings() == {}
    assert load_profiles(dump_profiles({"B": shape}))["B"] == shape


def test_baseout_fit_signs():
    hdr = "events,delta_run_exp,outs_when_up,on_1b,on_2b,on_3b\n"
    rows = ["strikeout,-0.5,1,0,0,1"] * 3 + ["strikeout,-0.2,0,0,0,0"] * 3 + ["field_out,0.1,1,0,0,1"] * 3 + ["single,0.4,0,0,0,0"] * 3
    t = fit([hdr + "\n".join(rows) + "\n"])
    assert t["states"][state_key(1, False, False, True)]["K"][0] < 0
    assert outcome_class("walk") == "BB" and outcome_class("field_out") == "BIP" and outcome_class("truncated_pa") is None


def test_arsenal_basis_by_pitch_count_and_live_drift():
    rows = [PitchRow("p", "2025-05-01", "FF", 1, 95, 16, 0, -4.5, pitch_count=10) for _ in range(150)]
    rows += [PitchRow("p", "2025-05-01", "FF", 3, 91, 16, 0, -4.5, pitch_count=95) for _ in range(60)]
    early = arsenal_for_state(rows, "2025-07-01", PitcherState(pitch_count=15), ArsenalBasis.PITCH_COUNT)
    late = arsenal_for_state(rows, "2025-07-01", PitcherState(pitch_count=95), ArsenalBasis.PITCH_COUNT)
    assert late["FF"].velo < early["FF"].velo
    drift = arsenal_for_state(rows, "2025-07-01", PitcherState(fb_drift=-2.0), ArsenalBasis.ALL_INNINGS, use_live_drift=True)
    base = arsenal_for_state(rows, "2025-07-01", PitcherState(), ArsenalBasis.ALL_INNINGS)
    assert abs((base["FF"].velo - drift["FF"].velo) - 2.0) < 1e-9


def test_usage_depends_on_batter_side_and_strike_count():
    from gameplan.shape import build_arsenal
    rows = []
    for i in range(300):
        rows.append(PitchRow("p", "2025-05-01", "FF", 1, 95, 16, 0, -4.5, stand="R", strikes=0))
    for i in range(100):
        rows.append(PitchRow("p", "2025-05-01", "SL", 1, 86, 2, 8, -6, stand="R", strikes=2))
    for i in range(100):
        rows.append(PitchRow("p", "2025-05-01", "CH", 1, 87, 8, -10, -6, stand="L", strikes=0))
    base = build_arsenal(rows, "2025-07-01")
    two_k = build_arsenal(rows, "2025-07-01", strikes=2)
    vs_l = build_arsenal(rows, "2025-07-01", stand="L")
    assert two_k["SL"].usage > base["SL"].usage
    assert vs_l["CH"].usage > base["CH"].usage


def test_filter_starts_drops_relief_outings():
    from gameplan.shape import filter_starts
    start = [PitchRow("p", "d", "FF", 1, 95, 16, 0, -4.5, game_pk="1", at_bat=a, pitch_no=1, inning=1 if a == 1 else 2)
             for a in (1, 2, 3)]
    relief = [PitchRow("p", "d", "FF", 1, 95, 16, 0, -4.5, game_pk="2", at_bat=a, pitch_no=1, inning=7)
              for a in (30, 31)]
    kept = filter_starts(start + relief)
    assert {r.game_pk for r in kept} == {"1"} and len(kept) == 3


def test_called_strike_model_learns_count_dependence():
    from gameplan.zone import CalledStrikeModel
    rnd = random.Random(0)
    rows = []
    for _ in range(3000):
        strikes = rnd.choice([0, 2])
        p = 0.8 if strikes == 0 else 0.3            # borderline pitch, called strike far more often at 0 strikes
        call = "strike" if rnd.random() < p else "ball"
        rows.append(SwingRow("h", "d", "FF", 0.85, 2.5, 14, -5, 93, None, False, x_away=0.85, swing=False,
                             take_call=call, strikes=strikes, sz_bot=1.5, sz_top=3.5))
    m = CalledStrikeModel(rows)
    assert m(0.85, 2.5, 1.5, 3.5, 0) > m(0.85, 2.5, 1.5, 3.5, 2) + 0.3


def test_hitter_level_term_moves_a_sparse_region_toward_the_hitters_overall_tendency():
    league = _swings(4000, 1, 0.25)
    high_whiff_hitter = [SwingRow("h", "d", "FF", rnd_x, 2.0, 14, -5, 93, None if w else 0.3, w, x_away=rnd_x, hb=0.0)
                         for rnd_x, w in [(-1.0 + i * 0.01, (i % 10) < 5) for i in range(300)]]   # whiffs 50%, only on the inside
    m = ContactModel(high_whiff_hitter, league, mode="shape")
    assert m.offset["whiff"] > 0.05                                     # overall he whiffs far more than league
    far = [[1.2, 3.8, 93, 14, 0, -5]]                                     # nowhere near any of his swings
    with_term = m.predict(far)["whiff"][0]
    m.offset = {k: 0.0 for k in m.offset}
    assert with_term > m.predict(far)["whiff"][0] + 0.03                 # sparse region still reflects him
