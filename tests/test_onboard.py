import numpy as np

from gameplan.onboard import build_map, compare_systems, suggest_map


def fake_export(n=1500, seed=0, speed=1.0, plate=12.0, flip=False, batter_relative=False):
    """Synthetic fastball-heavy export using the 2025 MLB signs (catcher-view pfx_x: RHP negative, LHP positive)."""
    rnd = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        s, p = rnd.choice(["Right", "Left"], p=[0.55, 0.45]), rnd.choice(["Right", "Left"], p=[0.7, 0.3])
        pfx = (-0.85 if p == "Right" else 0.9) + rnd.normal(0, 0.4)
        if batter_relative:
            pfx = abs(pfx) if p == s else -abs(pfx)
        rows.append({"RelSpeed": rnd.normal(93, 3) * speed, "PlateLocSide": (rnd.normal(0.18 if s == "Right" else -0.15, 0.8)) * plate * (-1 if flip else 1),
                     "PlateLocHeight": rnd.normal(2.4, 0.9) * 0.3048, "InducedVertBreak": rnd.normal(1.2, 0.6) * 12,
                     "HorzBreak": pfx * 12 * (-1 if flip else 1), "BatterSide": s, "PitcherThrows": p, "TaggedPitchType": "Fastball",
                     "PitchCall": "BallCalled", "Balls": 0, "Strikes": 0, "PAofInning": i, "PitchofPA": 1, "Inning": 1,
                     "GameID": "g", "Date": "2026-04-01", "BatterId": "b", "PitcherId": "p"})
    return rows


def test_header_mapping_proposes_common_names_and_lists_what_is_missing():
    rows = fake_export(10)
    got = suggest_map(list(rows[0].keys()))
    assert got["columns"]["velo"] == "RelSpeed" and got["columns"]["plate_z"] == "PlateLocHeight" and got["columns"]["call"] == "PitchCall"
    assert got["missing_required"] == []
    assert "plate_x" in suggest_map(["Foo", "PlateLocSide"])["columns"] and suggest_map(["Foo"])["missing_required"]


def test_units_and_sign_conventions_are_recovered_from_the_data():
    rows = fake_export()
    cmap, notes = build_map(rows, list(rows[0].keys()), "TrackMan")
    assert cmap.units["velo"] == "kph" or cmap.units["velo"] == "mph"           # 93 mph scaled by speed=1 is mph
    assert cmap.units["plate_x"] == "in" and cmap.units["plate_z"] == "m" and cmap.units["hb"] == "in" and cmap.units["ivb"] == "in"
    assert cmap.hb_convention == "catcher_view" and cmap.hb_sign == 1.0 and cmap.plate_x_sign == 1.0
    kph, _ = build_map(fake_export(speed=1.60934), list(rows[0].keys()))
    assert kph.units["velo"] == "kph"
    flipped, _ = build_map(fake_export(flip=True), list(rows[0].keys()))
    assert flipped.plate_x_sign == -1.0 and flipped.hb_sign == -1.0
    rel, _ = build_map(fake_export(batter_relative=True), list(rows[0].keys()))
    assert rel.hb_convention == "batter_relative"


def test_system_offset_is_estimated_from_pitchers_in_both_systems():
    rnd = np.random.default_rng(1)
    bases = [92 + rnd.normal(0, 2) for _ in range(12)]          # the same pitchers throw in both systems' parks

    def side(shift):
        out = []
        for p, base in enumerate(bases):
            for _ in range(40):
                out.append({"pitcher": f"p{p}", "pitch_type": "FF", "release_speed": str(base + shift + rnd.normal(0, 1)), "plate_z": "2.5"})
        return out
    off = compare_systems(side(0.0), side(0.5), ["release_speed"])
    assert 0.3 < off["release_speed"]["offset"] < 0.7 and off["release_speed"]["ci"][0] < 0.5 < off["release_speed"]["ci"][1]
    assert compare_systems(side(0.0)[:20], side(0.5)[:20], ["release_speed"]) == {}      # too few shared pitchers
