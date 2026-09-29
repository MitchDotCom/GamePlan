import csv
import io
import random

import pytest

from gameplan.evla import EvLaXwoba, EV_EDGES, LA_EDGES
from gameplan.milb import ColumnMap, convert, estimate_offsets, infer_profile
from gameplan.profiles import DataProfile, Tier
from gameplan.savant import parse_swings
from gameplan.shape import parse_pitches

COLS = {
    "game_id": "G", "date": "D", "batter_id": "B", "pitcher_id": "P", "stand": "BS", "p_throws": "PT", "balls": "Bl",
    "strikes": "St", "at_bat": "PA", "pitch_no": "PN", "inning": "In", "pitch_type": "Ty", "velo": "V",
    "plate_x": "X", "plate_z": "Z", "call": "C", "ivb": "IVB", "hb": "HB", "launch_speed": "EV", "launch_angle": "LA",
}
HEADER = list(COLS.values())


def export(n_pa=40, seed=0, hb_unit_scale=1.0, calls=("B", "C", "S", "F", "X")):
    rnd = random.Random(seed)
    rows = []
    for pa in range(1, n_pa + 1):
        for pn in range(1, 5):
            rows.append({"G": "g1", "D": "2026-04-10", "B": f"b{pa % 9}", "P": "p1", "BS": "Right" if pa % 2 else "Left",
                         "PT": "Right", "Bl": 0, "St": 0, "PA": pa, "PN": pn, "In": 1 + pa // 12, "Ty": "FF",
                         "V": round(rnd.gauss(89, 6), 1), "X": round(rnd.gauss(0, 0.7), 2), "Z": round(rnd.gauss(2.5, 0.8), 2),
                         "C": rnd.choice(calls), "IVB": round(rnd.gauss(14, 8), 1), "HB": round(rnd.gauss(0, 9) * hb_unit_scale, 1),
                         "EV": round(rnd.gauss(88, 12), 1), "LA": round(rnd.gauss(12, 25), 1)})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEADER)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


CMAP = ColumnMap(COLS, {"plate_x": "ft", "plate_z": "ft", "ivb": "in", "hb": "in", "velo": "mph"},
                 {"stand": {"Right": "R", "Left": "L"}, "p_throws": {"Right": "R", "Left": "L"}}, "catcher_view", 1.0, "TrackMan")


def test_conversion_round_trips_through_the_existing_parsers_with_correct_units():
    text, rep = convert(export(), CMAP, xwoba_model=EvLaXwoba(__import__("numpy").full((len(EV_EDGES) - 1, len(LA_EDGES) - 1), 0.3)))
    swings = parse_swings(text, include_takes=True)
    assert swings and rep["rows_out"] == rep["rows_in"] and not rep["unmapped_calls"]
    hbs = [s.hb for s in swings if s.hb is not None]
    assert 6 < (sum(h * h for h in hbs) / len(hbs)) ** 0.5 < 13            # inches, SD near the 9 put in
    ivb = [p.ivb for p in parse_pitches(text)]
    assert 5 < (sum((v - 14) ** 2 for v in ivb) / len(ivb)) ** 0.5 < 11
    assert not rep["warnings"]


def test_batter_relative_break_uses_the_measured_savant_sign_convention():
    one = "G,D,B,P,BS,PT,Bl,St,PA,PN,In,Ty,V,X,Z,C,IVB,HB,EV,LA\n" + "g,2026-04-01,b,p,{s},Right,0,0,1,1,1,FF,90,0,2.5,B,10,{hb},80,10\n"
    r_hitter, _ = convert(one.format(s="Right", hb=12), CMAP)
    l_hitter, _ = convert(one.format(s="Left", hb=12), CMAP)
    rows_r, rows_l = list(csv.DictReader(io.StringIO(r_hitter))), list(csv.DictReader(io.StringIO(l_hitter)))
    assert float(rows_r[0]["api_break_x_batter_in"]) == -1.0 and float(rows_l[0]["api_break_x_batter_in"]) == 1.0


def test_unit_mistakes_are_caught_by_the_sanity_check():
    text, rep = convert(export(hb_unit_scale=12.0), CMAP)          # inches, but declared as inches after being 12x too large
    assert any("api_break_x_batter_in" in w for w in rep["warnings"])
    wrong = ColumnMap({**COLS}, {"plate_x": "ft", "plate_z": "ft", "ivb": "in", "hb": "ft", "velo": "mph"},
                      CMAP.values, "catcher_view", 1.0, "TrackMan")     # says feet, data are inches
    _, rep2 = convert(export(), wrong)
    assert any("api_break_x_batter_in" in w for w in rep2["warnings"])


def test_nothing_is_silently_dropped_or_guessed():
    with pytest.raises(ValueError, match="unmapped call"):
        convert(export(calls=("B", "Q")), CMAP)
    with pytest.raises(ValueError, match="required"):
        ColumnMap({k: v for k, v in COLS.items() if k != "plate_z"}).check()
    with pytest.raises(ValueError, match="lacks mapped"):
        convert(export().replace("IVB", "IVX"), CMAP)


def test_times_through_the_order_are_derived_from_the_sequence():
    text, _ = convert(export(n_pa=30), CMAP)
    rows = list(csv.DictReader(io.StringIO(text)))
    by_batter = {}
    for r in rows:
        by_batter.setdefault(r["batter"], set()).add((int(r["at_bat_number"]), int(r["n_thruorder_pitcher"])))
    first = min(by_batter["b1"])
    assert first[1] == 1 and max(by_batter["b1"])[1] >= 2                  # same batter seen again later gets a higher TTO


def test_profile_inference_and_offsets_and_xwoba_fill():
    prof = infer_profile(CMAP, "Visalia")
    assert isinstance(prof, DataProfile) and prof.has_batted_ball and not prof.has_pitch_shape       # no VAA source mapped
    assert prof.tier() is Tier.BASIC
    shifted = DataProfile("x", offsets={"plate_z_ft": 0.5})
    a, _ = convert(export(seed=3), CMAP)
    b, _ = convert(export(seed=3), CMAP, profile=shifted)
    za = float(next(csv.DictReader(io.StringIO(a)))["plate_z"])
    zb = float(next(csv.DictReader(io.StringIO(b)))["plate_z"])
    assert abs((zb - za) - 0.5) < 1e-6
    ra, rb = list(csv.DictReader(io.StringIO(a))), list(csv.DictReader(io.StringIO(b)))
    est = estimate_offsets(ra, rb, ["plate_z"])
    assert abs(est["plate_z"]["offset"] - 0.5) < 1e-6 and est["plate_z"]["n"] == len(ra)
