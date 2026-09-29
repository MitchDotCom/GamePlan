import random

from gameplan import Hitter, Instruction, Pitcher, generate_grid_plan
from gameplan.savant import approach_angle, build_url, fit_hitter_model, parse_swings

HDR = "pitch_type,batter,description,plate_x,plate_z,pfx_z,release_speed,estimated_woba_using_speedangle,woba_value,vy0,vz0,ay,az\n"


def make_csv(seed=0):
    rnd = random.Random(seed)
    rows = []
    for b in ("1", "2", "3"):
        for _ in range(400):
            z = rnd.uniform(1.0, 4.0)
            x = rnd.uniform(-1.2, 1.2)
            desc = rnd.choice(["swinging_strike", "foul", "hit_into_play", "ball", "hit_into_play"])
            xw = 0.45 if (b == "1" and z < 2.0) else 0.30  # hitter 1 crushes low pitches
            rows.append(f"FF,{b},{desc},{x:.2f},{z:.2f},1.3,94,{xw},,-137,-5,28,-15")
    return HDR + "\n".join(rows) + "\n"


def test_parse_keeps_swings_only():
    swings = parse_swings(make_csv())
    assert swings and all(s.value >= 0 for s in swings)
    assert len(swings) < 1200


def test_approach_angle_is_negative_and_plausible():
    a = approach_angle({"vy0": "-137", "vz0": "-5", "ay": "28", "az": "-15"})
    assert -8 < a < -3


def test_build_url():
    u = build_url(665742, 2025, ["FF", "SL"])
    assert "batters_lookup%5B%5D=665742" in u and "FF%7CSL%7C" in u


def test_shrinkage_pulls_small_samples_to_league():
    m = fit_hitter_model(make_csv(), "1", k=30)
    league_low = fit_hitter_model(make_csv(), "2", k=30)
    assert m(0, 1.5, "FF") > league_low(0, 1.5, "FF")
    heavy = fit_hitter_model(make_csv(), "1", k=10_000)
    assert abs(heavy(0, 1.5, "FF") - league_low(0, 1.5, "FF")) < 0.05


def test_model_feeds_plan_generator():
    m = fit_hitter_model(make_csv(), "1", k=30)
    h = Hitter("1", baseline_xwoba=m.hitter_baseline)
    plan = generate_grid_plan(h, Pitcher("p"), m, ["FF"])
    go = [r for r in plan.rules if r.instruction is Instruction.GO]
    low = [r for r in go if r.zone.z_min < 2.2]
    assert low and len(low) > len(go) - len(low)  # signal dominates, some noise cells remain
