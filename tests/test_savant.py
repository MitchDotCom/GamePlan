import random

from gameplan import Hitter, Instruction, Pitcher, generate_grid_plan
from gameplan.savant import approach_angle, build_url, fit_hitter_model, parse_swings

HDR = "pitch_type,batter,game_date,description,plate_x,plate_z,pfx_z,release_speed,estimated_woba_using_speedangle,woba_value,vy0,vz0,ay,az\n"


def make_csv(seed=0, hitters=("1", "2", "3"), n=400):
    """Hitter '1' hits the ball hard on low pitches and whiffs a lot up; everyone else is flat."""
    rnd = random.Random(seed)
    rows = []
    for b in hitters:
        for i in range(n):
            z = rnd.uniform(1.0, 4.0)
            x = rnd.uniform(-1.2, 1.2)
            date = f"2025-{4 + i * 5 // n:02d}-{1 + i % 28:02d}"
            if b == "1":
                whiff_p = 0.10 if z < 2.0 else 0.45
            else:
                whiff_p = 0.25
            u = rnd.random()
            if u < whiff_p:
                desc = "swinging_strike"
            elif u < whiff_p + 0.2:
                desc = "foul"
            elif u < 0.97:
                desc = "hit_into_play"
            else:
                desc = "ball"
            xw = 0.55 if (b == "1" and z < 2.0) else 0.30
            rows.append(f"FF,{b},{date},{desc},{x:.2f},{z:.2f},1.3,94,{xw},,-137,-5,28,-15")
    return HDR + "\n".join(rows) + "\n"


def test_parse_keeps_swings_only():
    swings = parse_swings(make_csv())
    assert swings and len(swings) < 1200
    assert all(s.xwoba is None for s in swings if s.whiff)
    assert any(s.xwoba is not None for s in swings)


def test_contact_quality_penalizes_whiffs():
    from gameplan.savant import SwingRow, contact_quality
    hit = SwingRow("1", "d", "FF", 0, 2, 0, 0, 94, 0.400, False)
    miss = SwingRow("1", "d", "FF", 0, 2, 0, 0, 94, None, True)
    assert abs(contact_quality([hit, hit]) - 0.400) < 1e-9
    assert abs(contact_quality([hit, miss]) - 0.200) < 1e-9
    assert contact_quality([miss]) is None


def test_approach_angle_is_negative_and_plausible():
    a = approach_angle({"vy0": "-137", "vz0": "-5", "ay": "28", "az": "-15"})
    assert -8 < a < -3


def test_build_url():
    u = build_url(665742, 2025, ["FF", "SL"])
    assert "batters_lookup%5B%5D=665742" in u and "FF%7CSL%7C" in u


def test_shrinkage_pulls_small_samples_to_league():
    m = fit_hitter_model(make_csv(), "1")
    league_low = fit_hitter_model(make_csv(), "2")
    assert m(0, 1.5, "FF") > league_low(0, 1.5, "FF")
    heavy = fit_hitter_model(make_csv(), "1", k_swing=10_000, k_bip=10_000)
    assert abs(heavy(0, 1.5, "FF") - league_low(0, 1.5, "FF")) < 0.05


def test_model_feeds_plan_generator():
    m = fit_hitter_model(make_csv(), "1")
    h = Hitter("1", baseline_cq=m.hitter_cq, baseline_xwobacon=m.hitter_xwobacon)
    plan = generate_grid_plan(h, Pitcher("p"), m, ["FF"])
    go = [r for r in plan.rules if r.instruction is Instruction.GO]
    low = [r for r in go if r.zone.z_min < 2.2]
    assert low and len(low) > len(go) - len(low)  # signal dominates, some noise cells remain


def test_two_baselines_are_on_different_scales():
    m = fit_hitter_model(make_csv(), "2")
    assert m.hitter_cq < m.hitter_xwobacon  # whiffs pull CQ below xwOBA on contact
