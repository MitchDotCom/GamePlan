"""The comparison-pitcher finder: parsing an export, the pool, and a ranking a person can trust enough to overrule."""
import csv
import json
import math
import random

import pytest

from gameplan.engine import comps


@pytest.fixture(scope="module")
def pool():
    return comps.load_pool()


def mk(hand="R", z=5.9, x=2.0, ext=6.3, arm=35.0, pitches=None):
    pitches = pitches or {"FF": (0.55, 93, 8, 16), "SL": (0.25, 85, 3, 2), "CH": (0.20, 86, 14, 6)}
    return dict(name="T", hand=hand, n=0, rel_z=z, rel_x=x, ext=ext, arm_angle=arm,
                pitches={t: dict(usage=u, velo=v, hb=h, ivb=i, n=100) for t, (u, v, h, i) in pitches.items()}, warnings=[])


# ------------------------------------------------------------------ the pool itself
def test_pool_is_complete_and_sane(pool):
    P = pool["pitchers"]
    assert len(P) >= 300 and len({p["id"] for p in P}) == len(P)
    assert all(p["name"] and not p["name"].startswith("Pitcher ") for p in P), "every pitcher has a real name"
    assert {p["hand"] for p in P} == {"L", "R"} and sum(p["hand"] == "L" for p in P) > 80
    assert all(0.5 < p["rel_z"] < 7.2 and 4.5 < p["ext"] < 8.0 and 0 < p["rel_x"] < 5 for p in P)
    assert all(0 < sum(t["usage"] for t in p["pitches"].values()) <= 1.001 for p in P)
    assert sum(p["starts"] >= 5 for p in P) > 150


def test_known_pitchers_are_where_they_should_be(pool):
    by = {p["name"]: p for p in pool["pitchers"]}
    skubal, webb = by["Tarik Skubal"], by["Logan Webb"]
    assert skubal["hand"] == "L" and webb["hand"] == "R"
    assert skubal["arm_angle"] > webb["arm_angle"] + 15                 # Webb is a low-slot sinkerballer, Skubal a high-slot lefty
    assert "SI" in webb["pitches"] and webb["pitches"]["SI"]["usage"] > 0.3


def test_every_pitcher_ranks_first_against_his_own_profile(pool):
    rnd = random.Random(1)
    for p in rnd.sample(pool["pitchers"], 40):
        top = comps.rank(p, pool, n=1, starters_only=False)[0]
        assert top["id"] == p["id"] and top["total"] == pytest.approx(0, abs=1e-9)


def test_same_hand_is_required_unless_asked_otherwise(pool):
    t = mk("L")
    assert {r["hand"] for r in comps.rank(t, pool, n=30)} == {"L"}
    assert {r["hand"] for r in comps.rank(t, pool, n=300, same_hand=False)} == {"L", "R"}


def test_position_players_who_pitched_are_not_offered_by_default(pool):
    pos = [p for p in pool["pitchers"] if p.get("starts", 0) < 5]
    assert pos, "the pool does include relievers and position players"
    offered = {r["id"] for r in comps.rank(mk("R"), pool, n=1000)}
    assert not offered & {p["id"] for p in pos}
    assert {r["id"] for r in comps.rank(mk("R"), pool, n=1000, starters_only=False)} >= {p["id"] for p in pos if p["hand"] == "R"}


def test_exclude_ids_removes_the_pitcher_himself(pool):
    p = pool["pitchers"][0]
    assert p["id"] not in {r["id"] for r in comps.rank(p, pool, n=50, starters_only=False, exclude_ids={p["id"]})}


# ------------------------------------------------------------------ what the score means
def test_closer_arm_and_arsenal_means_a_lower_score(pool):
    sc = pool["scale"]
    base = pool["pitchers"][5]
    near = json.loads(json.dumps(base))
    far = json.loads(json.dumps(base))
    near["rel_z"] += 0.1
    far["rel_z"] += 1.0
    far["ext"] += 1.0
    for t in far["pitches"].values():
        t["velo"] += 6
    assert comps.distance(base, near, sc)["total"] < comps.distance(base, far, sc)["total"]


def test_a_pitch_the_comp_does_not_throw_is_expensive_and_an_extra_pitch_costs_its_usage(pool):
    sc = pool["scale"]
    t = mk(pitches={"FF": (0.6, 94, 8, 16), "KN": (0.4, 75, 2, 0)})
    comp = next(p for p in pool["pitchers"] if "KN" not in p["pitches"] and p["hand"] == "R")
    d = comps.distance(t, comp, sc)
    kn = next(r for r in d["pitches"] if r["type"] == "KN")
    assert kn["missing"] and d["arsenal"] >= 0.4 * comps.MISS
    only_ff = mk(pitches={"FF": (1.0, 94, 8, 16)})
    comp2 = next(p for p in pool["pitchers"] if len(p["pitches"]) >= 4 and p["hand"] == "R")
    assert comps.distance(only_ff, comp2, sc)["extra_usage"] > 0.1


def test_missing_arm_fields_are_left_out_not_treated_as_zero(pool):
    sc = pool["scale"]
    comp = pool["pitchers"][3]
    t = json.loads(json.dumps(comp))
    t["arm_angle"] = None
    t["rel_z"] = None
    d = comps.distance(t, comp, sc)
    assert set(d["arm_diffs"]) == {"rel_x", "ext"} and d["total"] == pytest.approx(0, abs=1e-9)
    none = json.loads(json.dumps(t))
    for k in ("rel_x", "ext"):
        none[k] = None
    assert comps.distance(none, comp, sc)["arm"] == 0.0


def test_ranking_is_deterministic_and_ties_break_on_id(pool):
    a = [r["id"] for r in comps.rank(mk(), pool, n=20)]
    assert a == [r["id"] for r in comps.rank(mk(), pool, n=20)]
    assert comps.rank(mk(), pool, n=3)[0]["total"] <= comps.rank(mk(), pool, n=3)[2]["total"]


def test_empty_target_is_refused(pool):
    with pytest.raises(ValueError):
        comps.rank(dict(hand="R", pitches={}), pool)


# ------------------------------------------------------------------ reading an export
def statcast_rows(n=200, hand="R"):
    rows = []
    for i in range(n):
        t = "FF" if i % 3 else "SL"
        rows.append({"pitch_type": t, "p_throws": hand, "release_speed": 93 - (8 if t == "SL" else 0) + (i % 4) * .3, "release_pos_x": -2.0 if hand == "R" else 2.0, "release_pos_z": 5.9, "release_extension": 6.4,
                     "arm_angle": 31.0, "pfx_x": -0.7 if t == "FF" else 0.2, "pfx_z": 1.3 if t == "FF" else 0.1, "player_name": "Doe, John"})
    return rows


def test_statcast_export_units_and_fields():
    p = comps.profile_from_rows(statcast_rows())
    assert p["hand"] == "R" and p["rel_x"] == 2.0 and p["arm_angle"] == 31.0 and p["n"] == 200 and not p["warnings"]
    ff = p["pitches"]["FF"]
    assert ff["usage"] == pytest.approx(133 / 200, abs=.01) and ff["ivb"] == pytest.approx(15.6, abs=.01) and ff["hb"] == pytest.approx(8.4, abs=.01)    # feet to inches; horizontal break compared by size


def test_lefty_release_side_sign_does_not_matter():
    a = comps.profile_from_rows(statcast_rows(hand="L"))
    assert a["hand"] == "L" and a["rel_x"] == 2.0
    flipped = [dict(r, release_pos_x=-r["release_pos_x"]) for r in statcast_rows(hand="L")]
    assert comps.profile_from_rows(flipped)["rel_x"] == 2.0


def test_trackman_names_and_inches():
    rows = [{"PitcherThrows": "Left", "TaggedPitchType": "Fastball" if i % 2 else "Sweeper", "RelSpeed": 90 + i % 3, "RelHeight": 5.5, "RelSide": 2.1, "Extension": 6.0, "HorzBreak": -9 if i % 2 else 14, "InducedVertBreak": 17 if i % 2 else 0} for i in range(120)]
    p = comps.profile_from_rows(rows)
    assert p["hand"] == "L" and set(p["pitches"]) == {"FF", "ST"} and p["pitches"]["FF"]["hb"] == 9 and p["pitches"]["FF"]["ivb"] == 17
    assert any("arm angle" in w for w in p["warnings"])


def test_rare_pitches_and_unknown_types_are_ignored():
    rows = statcast_rows(300) + [{"pitch_type": "XX", "p_throws": "R", "release_speed": 70} for _ in range(100)] + [dict(statcast_rows(1)[0], pitch_type="CH") for _ in range(5)]
    p = comps.profile_from_rows(rows)
    assert set(p["pitches"]) == {"FF", "SL"}


def test_unusable_exports_say_why():
    with pytest.raises(ValueError, match="No usable pitches"):
        comps.profile_from_rows([{"a": 1}])
    with pytest.raises(ValueError, match="No usable pitches"):
        comps.profile_from_rows([])
    with pytest.raises(ValueError, match="No usable pitches"):
        comps.profile_from_rows([{"pitch_type": "FF", "release_speed": 93}] * 100)               # no throwing hand


def test_non_numeric_junk_in_an_export_does_not_crash():
    rows = statcast_rows(100)
    rows[3]["release_speed"] = "n/a"
    rows[4]["pfx_x"] = "--"
    rows[5]["release_pos_z"] = "NaN"
    p = comps.profile_from_rows(rows)
    assert p["rel_z"] == 5.9 and all(math.isfinite(t["velo"]) for t in p["pitches"].values())


def test_form_parsing():
    f = dict(hand="L", rel_z="5.5", rel_x="-2.1", ext="6.2", arm_angle="", t1="four-seam", u1="60", v1="92", h1="-8", i1="17", t2="CH", u2="0.4", v2="84", h2="", i2="")
    p = comps.profile_from_form(f)
    assert p["hand"] == "L" and p["rel_x"] == 2.1 and p["arm_angle"] is None and p["pitches"]["FF"]["usage"] == .6 and p["pitches"]["CH"]["usage"] == .4 and p["pitches"]["FF"]["hb"] == 8
    assert any("arm angle" in w for w in p["warnings"])
    for bad in (dict(f, hand=""), dict(f, t1="", t2=""), dict(f, v1="")):
        with pytest.raises(ValueError):
            comps.profile_from_form(bad)


# ------------------------------------------------------------------ building the pool
def test_build_pool_from_files_and_names(tmp_path):
    rows = []
    for pid, hand in (("11", "R"), ("22", "L"), ("33", "R")):
        for i in range(700 if pid != "33" else 100):                              # 33 throws too few pitches to enter
            rows.append({"pitcher": pid, "pitch_type": "FF" if i % 2 else "SL", "p_throws": hand, "release_speed": 90 + i % 3, "release_pos_x": 2, "release_pos_z": 5.5, "release_extension": 6,
                         "arm_angle": 30, "pfx_x": .5, "pfx_z": 1.2, "inning": 1 if i < 30 else 4, "game_pk": 100 + i // 30, "player_name": "Batter, Wrong"})
    with open(tmp_path / "2025-04-01.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = tmp_path / "pool.json"
    pool = comps.build_pool(str(tmp_path / "*.csv"), 2025, out, {11: "Right Guy", 22: "Left Guy"})
    assert [p["id"] for p in pool["pitchers"]] == [11, 22] and [p["name"] for p in pool["pitchers"]] == ["Right Guy", "Left Guy"]     # the batter's name in the file is never used
    assert pool["pitchers"][0]["starts"] == 1 and json.loads(out.read_text())["season"] == 2025
    assert comps.load_pool(out)["pitchers"][1]["hand"] == "L"


def test_fetch_names_chunks_and_survives_missing_people():
    calls = []

    def fake(url):
        calls.append(url)
        ids = [int(x) for x in url.split("personIds=")[1].split(",")]
        return {"people": [{"id": i, "fullName": f"N{i}"} for i in ids if i % 7]}

    got = comps.fetch_names(list(range(1, 401)), fake)
    assert len(calls) == 3 and got[1] == "N1" and 7 not in got and len(got) == 400 - 57
