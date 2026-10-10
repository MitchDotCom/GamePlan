"""Drawing a starter's pitches from an export: every way the file can be right, wrong, mirrored or hostile, and the checks that decide whether a pitch is drawn at all."""
import csv
import io
import json
import math
import pathlib
import statistics

import pytest

from gameplan import simview
from gameplan.engine import db, identity, pitchimport as PI, runner, schedule

FIX = pathlib.Path(__file__).parent / "fixtures"
TRACKMAN_TYPES = {"FF": "Fastball", "SI": "Sinker", "FC": "Cutter", "SL": "Slider", "ST": "Sweeper", "CU": "Curveball", "CH": "ChangeUp", "FS": "Splitter"}


def rows(name):
    return list(csv.DictReader(open(FIX / name)))


def dump(rs):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rs[0]))
    w.writeheader()
    w.writerows(rs)
    return out.getvalue()


def trackman(rs, flip_hb=False, flip_side=False, flip_plate=False):
    """The same pitches as a TrackMan-style export: other names, inches, words for hands, optional mirrored signs."""
    out = []
    for r in rs:
        out.append({"Date": r["game_date"], "TaggedPitchType": TRACKMAN_TYPES[r["pitch_type"]], "RelSpeed": r["release_speed"], "RelHeight": r["release_pos_z"],
                    "RelSide": str(float(r["release_pos_x"]) * (-1 if flip_side else 1)), "Extension": r["release_extension"],
                    "HorzBreak": str(round(float(r["pfx_x"]) * 12 * (-1 if flip_hb else 1), 2)), "InducedVertBreak": str(round(float(r["pfx_z"]) * 12, 2)),
                    "PlateLocSide": str(float(r["plate_x"]) * (-1 if flip_plate else 1)), "PlateLocHeight": r["plate_z"],
                    "PitcherThrows": "Right" if r["p_throws"] == "R" else "Left", "BatterSide": "Right" if r["stand"] == "R" else "Left"})
    return out


# ------------------------------------------------------------------ the physics
def true_gap(r, phys):
    """Largest distance (ft) between the rebuilt path and Statcast's own, a quarter, half and three quarters of the way to the plate."""
    t = simview.t_to_plane(phys)
    worst = 0
    for fr in (.25, .5, .75):
        s = t * fr
        d = [(phys["v" + c + "0"] - float(r["v" + c + "0"])) * s + .5 * (phys["a" + c] - float(r["a" + c])) * s * s for c in "xyz"]
        worst = max(worst, math.sqrt(sum(x * x for x in d)))
    return worst


@pytest.mark.parametrize("name", ["statcast_rhp.csv", "statcast_lhp.csv"])
def test_rebuilt_paths_track_statcasts_own_paths(name):
    gaps = []
    for r in rows(name):
        ph = PI.reconstruct(float(r["release_pos_x"]), float(r["release_pos_z"]), float(r["release_extension"]), float(r["release_speed"]), float(r["plate_x"]), float(r["plate_z"]), float(r["pfx_x"]), float(r["pfx_z"]))
        assert ph is not None
        gaps.append(true_gap(r, ph))
    gaps.sort()
    assert statistics.median(gaps) < 0.15 and gaps[int(len(gaps) * .95)] < 0.35 and gaps[-1] < 0.8, (statistics.median(gaps), gaps[int(len(gaps) * .95)], gaps[-1])


def test_a_rebuilt_path_reproduces_the_plate_location_and_speed():
    r = rows("statcast_rhp.csv")[0]
    ph = PI.reconstruct(float(r["release_pos_x"]), float(r["release_pos_z"]), float(r["release_extension"]), float(r["release_speed"]), float(r["plate_x"]), float(r["plate_z"]), float(r["pfx_x"]), float(r["pfx_z"]))
    t = simview.t_to_plane(ph)
    x, y, z = simview.position(ph, t)
    assert abs(x - float(r["plate_x"])) < 1e-6 and abs(z - float(r["plate_z"])) < 1e-6 and abs(y - 17 / 12) < 1e-6 and 0.35 < t < 0.5


def test_impossible_numbers_have_no_path():
    assert PI.reconstruct(-2, 5.8, 6.3, 20, 0, 2.5, 0, 0) is None            # 20 mph cannot cover the distance in a sane time
    assert PI.reconstruct(-2, 5.8, 6.3, 95, 0, 2.5, 0, 0) is not None           # and an ordinary fastball does have one


# ------------------------------------------------------------------ reading the file
@pytest.mark.parametrize("name,hand", [("statcast_rhp.csv", "R"), ("statcast_lhp.csv", "L")])
def test_statcast_style_file(name, hand):
    p = PI.parse(open(FIX / name).read())
    assert p["ok"] and p["summary"]["hand"] == hand and p["summary"]["accepted"] >= .97 * p["summary"]["total"] and p["summary"]["starts"] == 3 and p["dates"] == sorted(p["dates"], reverse=True)
    for r in p["rows"]:
        assert simview.sim_params(r)[0] is not None
        assert r["play_id"].startswith("imp") and len(r["play_id"]) == 12 and r["sz_top"] > r["sz_bot"]
    assert len({r["play_id"] for r in p["rows"]}) == len(p["rows"])
    assert not any("strike-zone" in w for w in p["warnings"])                      # this file carries each batter's zone


def test_a_file_with_no_zone_says_so_and_uses_a_fixed_one():
    p = PI.parse(dump(trackman(rows("statcast_rhp.csv"))))
    assert p["ok"] and any("strike-zone" in w and "3.4" in w for w in p["warnings"]) and {(r["sz_top"], r["sz_bot"]) for r in p["rows"]} == {(3.4, 1.6)}


def test_zone_from_the_file_is_used_per_batter():
    rs = rows("statcast_rhp.csv")
    for i, r in enumerate(rs):
        r["sz_top"], r["sz_bot"] = ("3.9", "1.8") if i % 2 else ("3.2", "1.4")
    p = PI.parse(dump(rs))
    assert p["ok"] and not any("strike-zone" in w for w in p["warnings"]) and {(r["sz_top"], r["sz_bot"]) for r in p["rows"]} == {(3.9, 1.8), (3.2, 1.4)}


@pytest.mark.parametrize("name", ["statcast_rhp.csv", "statcast_lhp.csv"])
def test_trackman_style_gives_the_same_drawn_pitches(name):
    base = rows(name)
    a = PI.parse(dump(base))
    b = PI.parse(dump(trackman(base)))
    assert b["ok"] and b["summary"]["accepted"] == a["summary"]["accepted"]
    ka = sorted((r["px"], r["pz"], r["pitch_type"]) for r in a["rows"])
    kb = sorted((r["px"], r["pz"], r["pitch_type"]) for r in b["rows"])
    assert ka == kb
    pa = {(r["px"], r["pz"]): r for r in a["rows"]}
    for r in b["rows"]:                                                           # same path to within the inch rounding of the break
        o = pa[(r["px"], r["pz"])]
        assert abs(r["ax"] - o["ax"]) < 1.2 and abs(r["az"] - o["az"]) < 1.2 and abs(r["vx0"] - o["vx0"]) < .6


@pytest.mark.parametrize("name", ["statcast_rhp.csv", "statcast_lhp.csv"])
def test_a_mirrored_break_column_is_detected_and_corrected(name):
    base = rows(name)
    straight = PI.parse(dump(trackman(base)))
    flipped = PI.parse(dump(trackman(base, flip_hb=True)))
    assert straight["ok"] and flipped["ok"]
    assert straight["summary"]["hb_direction"] == "as exported" and flipped["summary"]["hb_direction"] == "flipped"
    ps = sorted((r["px"], r["pz"], round(r["ax"], 1)) for r in straight["rows"])
    pf = sorted((r["px"], r["pz"], round(r["ax"], 1)) for r in flipped["rows"])
    assert ps == pf                                                               # the sideways curve is the same either way


def test_release_side_sign_does_not_matter():
    base = rows("statcast_rhp.csv")
    a = PI.parse(dump(trackman(base)))
    b = PI.parse(dump(trackman(base, flip_side=True)))
    assert sorted((r["px"], round(r["x0"], 3)) for r in a["rows"]) == sorted((r["px"], round(r["x0"], 3)) for r in b["rows"])


def test_plate_side_flag_undoes_a_mirrored_plate_column():
    base = rows("statcast_rhp.csv")
    a = PI.parse(dump(trackman(base)))
    b = PI.parse(dump(trackman(base, flip_plate=True)), plate_sign=-1)
    assert b["ok"] and sorted(r["px"] for r in a["rows"]) == sorted(r["px"] for r in b["rows"])
    c = PI.parse(dump(trackman(base, flip_plate=True)))                            # without the flag the mirrored pitches still hold together, which is why the page asks
    assert c["ok"] and sorted(r["px"] for r in c["rows"]) != sorted(r["px"] for r in a["rows"])


def test_full_path_numbers_are_used_as_given():
    base = rows("statcast_rhp.csv")[:150]
    out = []
    for r in base:
        ph = PI.reconstruct(float(r["release_pos_x"]), float(r["release_pos_z"]), float(r["release_extension"]), float(r["release_speed"]), float(r["plate_x"]), float(r["plate_z"]), float(r["pfx_x"]), float(r["pfx_z"]))
        out.append({**{k: r[k] for k in ("pitch_type", "release_speed", "p_throws", "stand", "plate_x", "plate_z")}, **{k: ph[k] for k in simview.FIELDS}})
    p = PI.parse(dump(out))
    assert p["ok"] and p["summary"]["path"] == "given" and p["summary"]["accepted"] >= 140 and all(r["pfxZ"] is not None for r in p["rows"])
    out[0]["vz0"] = "-10"                                                          # a path that no longer reaches the plate where the row says
    assert PI.parse(dump(out))["rejected"].get("failed the path checks: ball is not moving toward the plate throughout") or PI.parse(dump(out))["summary"]["rejected"] > 0


def test_rows_that_cannot_be_drawn_are_counted_with_reasons_not_drawn():
    rs = trackman(rows("statcast_rhp.csv"))
    rs[0]["TaggedPitchType"] = "Undefined"
    rs[1]["RelSpeed"] = "n/a"
    rs[2]["Extension"] = "1.2"
    rs[3]["HorzBreak"] = "400"
    rs[4]["PitcherThrows"] = ""
    rs[5]["PlateLocSide"] = "9"
    p = PI.parse(dump(rs))
    assert p["ok"] and p["summary"]["rejected"] == 6 and len(p["rejected"]) >= 4
    assert "unknown pitch type" in p["rejected"] and any("release point" in k for k in p["rejected"]) and any("break" in k for k in p["rejected"])


# ------------------------------------------------------------------ refused files
def test_refusals_say_what_is_wrong():
    good = trackman(rows("statcast_rhp.csv"))
    assert "missing" in PI.parse("a,b\n1,2\n")["error"] and "plate side" in PI.parse("a,b\n1,2\n")["error"]
    assert "no rows" in PI.parse("")["error"] or "no rows" in PI.parse("RelSpeed\n")["error"]
    assert "release height" in PI.parse(dump([{k: v for k, v in r.items() if k not in ("HorzBreak", "InducedVertBreak")} for r in good]))["error"]
    two = [dict(r, Pitcher="A") for r in good[:100]] + [dict(r, Pitcher="B") for r in good[100:200]]
    assert "2 different pitchers" in PI.parse(dump(two))["error"]
    mixed = [dict(r) for r in good]
    for r in mixed[::2]:
        r["PitcherThrows"] = "Left"
    assert "mixes left- and right-handed" in PI.parse(dump(mixed))["error"]
    assert "Only" in PI.parse(dump(good[:30]))["error"]
    assert "larger than 5 MB" in PI.parse("x" * 5_100_000)["error"]
    assert PI.parse("\x00\x01garbage\n\x02")["error"]


def test_ambiguous_break_direction_is_refused_not_guessed():
    rs = trackman(rows("statcast_rhp.csv"))
    for r in rs:
        r["HorzBreak"] = str(abs(float(r["HorzBreak"])) + 2)                       # everything runs the same way: the direction cannot be read
    p = PI.parse(dump(rs))
    assert not p["ok"] and "Cannot tell which way horizontal break points" in p["error"]
    for r in rs:
        r["HorzBreak"] = "0.2"
    assert "Cannot tell" in PI.parse(dump(rs))["error"]


def test_meters_or_wrong_units_are_not_drawn():
    rs = trackman(rows("statcast_rhp.csv"))
    for r in rs:
        r["RelHeight"] = str(float(r["RelHeight"]) * 0.3048)
        r["Extension"] = str(float(r["Extension"]) * 0.3048)
    p = PI.parse(dump(rs))
    assert not p["ok"] and "release point" in p["error"]


def test_hostile_cells_are_just_text():
    rs = trackman(rows("statcast_rhp.csv"))
    rs[0]["TaggedPitchType"] = "=cmd|' /C calc'!A0"
    rs[1]["Date"] = "<script>alert(1)</script>"
    p = PI.parse(dump(rs))
    assert p["ok"] and "<script" not in json.dumps(p["rows"]) and p["rejected"].get("unknown pitch type") == 1


# ------------------------------------------------------------------ storage and the build
@pytest.fixture
def imported(conn, org, tmp_path):
    p = PI.parse(dump(rows("statcast_rhp.csv")))
    PI.save(conn, 434378, p, None, "test export")
    return p


def test_save_replaces_and_load_roundtrips(conn, imported):
    again = PI.parse(dump(rows("statcast_rhp.csv")[:150]))
    PI.save(conn, 434378, again, None)
    got = PI.load(conn, 434378)
    assert len(got["rows"]) == again["summary"]["accepted"] and got["summary"]["hand"] == "R" and PI.load(conn, 1) is None
    assert conn.execute("SELECT COUNT(*) n FROM pitch_imports").fetchone()["n"] == 1


def test_materialize_writes_one_feed_per_start_and_playlist_reads_them(conn, imported, tmp_path):
    from gameplan import playlist as PL
    imp = PI.load(conn, 434378)
    starts = PI.materialize(imp, 434378, tmp_path / "feeds")
    assert len(starts) == 3 and [d for d, _ in starts] == sorted([d for d, _ in starts], reverse=True)
    pool = PL.pooled(434378, starts, tmp_path / "feeds")
    assert len(pool) == len(imp["rows"]) and all(p["pitcher"] == 434378 and p["type"] == "pitch" for p in pool)


def test_the_real_pipeline_builds_packs_from_an_export_with_no_network(conn, org, imported, tmp_path, monkeypatch):
    """No fake prepare here: the real gates run on drawn pitches built from the upload."""
    import socket

    def no_net(*a, **k):
        raise AssertionError("the build reached for the network")
    monkeypatch.setattr(socket, "create_connection", no_net)
    t = org["t1"]
    conn.execute("UPDATE teams SET adapter='tracking_drawn' WHERE id=?", (t,))
    sid = schedule.set_entry(conn, t, "2027-05-04", "Milb Arm", 434378)["id"]
    runner.build_queued(tmp_path / "engine.db", tmp_path / "data", limit=1)
    row = conn.execute("SELECT * FROM starters WHERE id=?", (sid,)).fetchone()
    assert row["build_state"] == "ready", (row["build_state"], row["build_detail"])
    assert "uploaded tracking" in row["build_detail"] and schedule.content_state(conn, sid) == "ready"
    pk = conn.execute("SELECT * FROM packs WHERE starter_id=? AND status='active' AND kind='starter' AND side='R'", (sid,)).fetchone()
    items = json.loads(pk["manifest_json"])["items"]
    assert len(items) >= 6 and all(i["sim"] and i["file"] is None and i["camera"] == "sim" for i in items) and pk["adapter"] == "tracking_drawn"
    assert {i["keys"]["strike"] for i in items} == {True, False}


def test_an_upload_makes_a_game_buildable_at_an_affiliate_with_no_pitch_source(conn, org, imported, tmp_path):
    t = identity.add_team(conn, "Rookie Club", "Rookie", None, None, "none")
    sid = schedule.set_entry(conn, t, "2027-05-04", "Milb Arm", 434378)["id"]
    assert conn.execute("SELECT build_state FROM starters WHERE id=?", (sid,)).fetchone()["build_state"] == ""
    conn.execute("UPDATE starters SET build_state='queued' WHERE id=?", (sid,))
    runner.build_queued(tmp_path / "engine.db", tmp_path / "data", limit=1)
    assert conn.execute("SELECT build_state FROM starters WHERE id=?", (sid,)).fetchone()["build_state"] == "ready"


def test_a_pitcher_with_no_upload_and_no_savant_history_is_reported_as_no_video(conn, org, tmp_path):
    sid = schedule.set_entry(conn, org["t1"], "2027-05-04", "Nobody", 999999)["id"]

    def prep(*a, **k):
        return dict(ok=False, built=True, gates=[dict(gate="build", status="FAIL", detail="no pitches for this starter", side=None)])
    runner.build_queued(tmp_path / "engine.db", tmp_path / "data", prep, limit=1)
    assert conn.execute("SELECT build_state FROM starters WHERE id=?", (sid,)).fetchone()["build_state"] == "no_video"
