"""The weekly slate: which starter a hitter sees, when it flips, and every way an admin can change it. Times are written in UTC; the comments give Pacific."""
import datetime as dt
import json
import random

import pytest

from gameplan.engine import db, identity, packs, playlist, schedule

from .test_answers_playlist import item
from .conftest import SECRET


def z(s):                                   # '2027-05-05T03:59:59' -> iso with microseconds
    return s + ".000000Z"


# 2027-05-04 is PDT (UTC-7): 21:00 Pacific = 04:00 UTC the next day
BEFORE = z("2027-05-05T03:59:59")           # 20:59:59 Pacific, May 4
AT = z("2027-05-05T04:00:00")               # 21:00:00 Pacific, May 4
NOON = z("2027-05-04T19:00:00")             # 12:00 Pacific, May 4


def bound(conn, tmp, team, starter_id, side="L", kind="starter", n=4, tag=""):
    its = [item(f"{kind}{side}{tag}{starter_id}_{i}", strike=bool(i % 2), pt=["FF", "SL", "CH"][i % 3]) for i in range(n)]
    pack = dict(id=f"p{kind}{side}{tag}{starter_id}", dir="p", title=f"{kind} {starter_id}", subtitle="", mode="train", items=its)
    return packs.register(conn, pack, kind, side, "test", tmp / "content", tmp / "src", team, starter_id, None)


def slate(conn, player, now):
    return playlist.compose(conn, player, now_iso=now, record=False)


def names(pl):
    return pl["slate"]["games"] and [g["starter"] for g in pl["slate"]["games"]]


@pytest.fixture
def week(conn, org):
    """Visalia has a different starter every night May 4 to 8, each with a built pack on both sides."""
    t = org["t1"]
    ids = {}
    for i, d in enumerate(["2027-05-04", "2027-05-05", "2027-05-06", "2027-05-07", "2027-05-08"]):
        r = schedule.set_entry(conn, t, d, f"Starter {d[-2:]}", 1000 + i, f"Opp {i}", None)
        ids[d] = r["id"]
    return ids


def hitter(conn, org, which="p1"):
    return conn.execute("SELECT * FROM players WHERE id=?", (org[which],)).fetchone()


# ------------------------------------------------------------------ the clock
def test_flips_at_exactly_nine_pacific(conn, org, week):
    p = hitter(conn, org)
    assert names(slate(conn, p, BEFORE)) == ["Starter 04"]
    assert names(slate(conn, p, AT)) == ["Starter 05"]
    assert names(slate(conn, p, NOON)) == ["Starter 04"]


def test_daylight_saving_edges(conn, org):
    t = org["t1"]
    for d in ("2027-03-13", "2027-03-14", "2027-03-15", "2027-11-06", "2027-11-07", "2027-11-08"):
        schedule.set_entry(conn, t, d, f"S{d[-5:]}", 1)
    # spring forward is Sunday 2027-03-14 02:00: Saturday night is PST (UTC-8), Sunday night is PDT (UTC-7)
    assert schedule.slate_day(conn, t, z("2027-03-14T04:59:59"))["date"] == "2027-03-13"      # 20:59:59 PST Saturday
    assert schedule.slate_day(conn, t, z("2027-03-14T05:00:00"))["date"] == "2027-03-14"      # 21:00 PST Saturday
    assert schedule.slate_day(conn, t, z("2027-03-15T03:59:59"))["date"] == "2027-03-14"      # 20:59:59 PDT Sunday
    assert schedule.slate_day(conn, t, z("2027-03-15T04:00:00"))["date"] == "2027-03-15"
    # fall back is Sunday 2027-11-07 02:00
    assert schedule.slate_day(conn, t, z("2027-11-07T03:59:59"))["date"] == "2027-11-06"      # 20:59:59 PDT Saturday
    assert schedule.slate_day(conn, t, z("2027-11-07T04:00:00"))["date"] == "2027-11-07"
    assert schedule.slate_day(conn, t, z("2027-11-08T04:59:59"))["date"] == "2027-11-07"      # 20:59:59 PST Sunday
    assert schedule.slate_day(conn, t, z("2027-11-08T05:00:00"))["date"] == "2027-11-08"


def test_other_zone_and_a_broken_zone_never_breaks_a_playlist(conn, org):
    t = org["t2"]
    conn.execute("UPDATE level_settings SET rollover_tz='America/New_York', rollover_hour=22 WHERE team_id=?", (t,))
    assert schedule.slate_day(conn, t, z("2027-05-05T01:59:59"))["date"] == "2027-05-04"      # 21:59:59 Eastern
    assert schedule.slate_day(conn, t, z("2027-05-05T02:00:00"))["date"] == "2027-05-05"
    conn.execute("UPDATE level_settings SET rollover_tz='Mars/Olympus', rollover_hour=3 WHERE team_id=?", (t,))
    assert schedule.slate_day(conn, t, AT)["date"] == "2027-05-05"                           # falls back to Pacific 21:00
    assert schedule.slate_day(conn, t, BEFORE)["date"] == "2027-05-04"


def test_valid_until_is_the_next_change(conn, org, week):
    sd = schedule.slate_day(conn, org["t1"], NOON)
    assert sd["valid_until"] == AT and sd["source"] == "clock"
    assert schedule.slate_day(conn, org["t1"], AT)["valid_until"] == z("2027-05-06T04:00:00")


def test_a_run_of_minutes_flips_once_a_day_and_never_goes_back(conn, org, week):
    t, seen, last = org["t1"], [], None
    now = parse = dt.datetime(2027, 5, 3, 18, 0, tzinfo=dt.timezone.utc)
    for k in range(0, 24 * 60 * 6, 7):
        d = schedule.resolve(conn, t, schedule.to_iso(now + dt.timedelta(minutes=k)))["game_date"]
        if d != last:
            seen.append((k, d))
            last = d
    assert [d for _, d in seen] == ["2027-05-04", "2027-05-05", "2027-05-06", "2027-05-07", "2027-05-08", None]
    flips = [k for k, _ in seen[1:-1]]
    assert all(abs((b - a) - 1440) <= 7 for a, b in zip(flips, flips[1:]))


# ------------------------------------------------------------------ what appears when
def test_off_days_and_gaps(conn, org):
    t, p = org["t1"], hitter(conn, org)
    schedule.set_entry(conn, t, "2027-05-04", "Mon off? no, game", 1)
    schedule.set_entry(conn, t, "2027-05-07", "Thursday Guy", 2)
    assert names(slate(conn, p, z("2027-05-05T04:00:00"))) == ["Thursday Guy"]          # May 5 slate, off days between: the next game shows
    assert slate(conn, p, z("2027-05-08T04:00:00"))["slate"]["games"] == []             # May 8 slate: Thursday's game is behind it, nothing after


def test_nothing_in_ten_days_is_said_plainly(conn, org):
    p = hitter(conn, org)
    schedule.set_entry(conn, org["t1"], "2027-06-30", "Far Away", 1)
    pl = slate(conn, p, NOON)
    assert pl["slate"]["games"] == [] and "Nothing is ready" in pl["notes"][0]


def test_doubleheader_shows_both_in_order(conn, org, tmp_path):
    t, p = org["t1"], hitter(conn, org)
    a = schedule.set_entry(conn, t, "2027-05-04", "Game One", 1, game_no=1)["id"]
    b = schedule.set_entry(conn, t, "2027-05-04", "Game Two", 2, game_no=2)["id"]
    bound(conn, tmp_path, t, a, "L")
    bound(conn, tmp_path, t, b, "L")
    pl = slate(conn, p, NOON)
    assert names(pl) == ["Game One", "Game Two"]
    assert [m["title"] for m in pl["packs"]] == [f"starter {a}", f"starter {b}"]


def test_a_pack_is_served_only_on_its_own_starters_days(conn, org, week, tmp_path):
    t, p = org["t1"], hitter(conn, org)
    mon, tue = week["2027-05-04"], week["2027-05-05"]
    hm, ht = bound(conn, tmp_path, t, mon), bound(conn, tmp_path, t, tue)
    assert [m["id"] for m in slate(conn, p, NOON)["packs"]] == [hm]
    assert [m["id"] for m in slate(conn, p, AT)["packs"]] == [ht]


def test_team_wide_pack_always_served_and_other_teams_never(conn, org, week, tmp_path):
    t, p = org["t1"], hitter(conn, org)
    team_wide = bound(conn, tmp_path, t, None, kind="edges", tag="tw")
    other = schedule.set_entry(conn, org["t2"], "2027-05-04", "Reno Guy", 77)["id"]
    ho = bound(conn, tmp_path, org["t2"], other)
    got = [m["id"] for m in slate(conn, p, NOON)["packs"]]
    assert team_wide in got and ho not in got


def test_unbuilt_starter_shows_practice_and_names_him(conn, org, week, tmp_path):
    p = hitter(conn, org)
    practice = packs.register(conn, dict(id="pr", dir="p", title="practice", subtitle="", mode="train", items=[item("prx0")]), "random", "L", "test", tmp_path / "content", tmp_path / "src", None, None, None, practice=True)
    pl = slate(conn, p, NOON)
    assert [m["id"] for m in pl["packs"]] == [practice]
    assert "Starter 04" in pl["notes"][0] and "not ready" in pl["notes"][0]


def test_switch_hitter_gets_both_sides(conn, org, tmp_path):
    t = org["t2"]
    e = schedule.set_entry(conn, t, "2027-05-04", "Lefty", 5)["id"]
    hl, hr = bound(conn, tmp_path, t, e, "L"), bound(conn, tmp_path, t, e, "R")
    pl = slate(conn, hitter(conn, org, "p3"), NOON)
    assert {m["id"] for m in pl["packs"]} == {hl, hr}


# ------------------------------------------------------------------ changing the schedule
def test_saving_the_same_thing_again_changes_nothing(conn, org, week):
    n = conn.execute("SELECT COUNT(*) n FROM starters").fetchone()["n"]
    r = schedule.set_entry(conn, org["t1"], "2027-05-04", "Starter 04", 1000, "Opp 0", None)
    assert r["changed"] is False and r["id"] == week["2027-05-04"]
    assert conn.execute("SELECT COUNT(*) n FROM starters").fetchone()["n"] == n


def test_a_scratch_replaces_the_starter_retires_his_packs_and_keeps_old_answers_valid(conn, org, week, tmp_path):
    t, p = org["t1"], hitter(conn, org)
    old = bound(conn, tmp_path, t, week["2027-05-04"])
    r = schedule.set_entry(conn, t, "2027-05-04", "Late Scratch Replacement", 9999, "Opp 0", None)
    assert r["changed"]
    assert conn.execute("SELECT status FROM packs WHERE hash=?", (old,)).fetchone()["status"] == "retired"
    assert conn.execute("SELECT status FROM starters WHERE id=?", (week["2027-05-04"],)).fetchone()["status"] == "superseded"
    assert names(slate(conn, p, NOON)) == ["Late Scratch Replacement"]
    assert conn.execute("SELECT COUNT(*) n FROM item_keys WHERE pack_hash=?", (old,)).fetchone()["n"] == 4        # keys stay so earlier answers still score


def test_postponed_game_drops_out_and_the_next_one_shows(conn, org, week):
    assert schedule.cancel_entry(conn, org["t1"], "2027-05-04", 1, None, "rain")
    assert names(slate(conn, hitter(conn, org), NOON)) == ["Starter 05"]
    assert conn.execute("SELECT status FROM starters WHERE id=?", (week["2027-05-04"],)).fetchone()["status"] == "rejected"
    assert not schedule.cancel_entry(conn, org["t1"], "2027-05-04", 1, None)


def test_validation(conn, org):
    t = org["t1"]
    bad = [("2027-13-01", "A", 1), ("May 4", "A", 1), ("2027-05-04", "  ", 1), ("2027-05-04", "A" * 200, 1), ("2027-05-04", "A", "12ab"), ("2027-05-04", "A", -4), ("2027-05-04", "A", "1" * 12)]
    for d, n, i in bad:
        with pytest.raises(identity.EngineError):
            schedule.set_entry(conn, t, d, n, i)
    with pytest.raises(identity.EngineError):
        schedule.set_entry(conn, t, "2027-05-04", "A", 1, game_no=4)
    with pytest.raises(identity.EngineError):
        schedule.set_entry(conn, 9999, "2027-05-04", "A", 1)
    assert conn.execute("SELECT COUNT(*) n FROM starters").fetchone()["n"] == 0


def test_strict_window_catches_the_wrong_year(conn, org):
    t = org["t1"]
    with pytest.raises(identity.EngineError, match="outside the window"):
        with db.tx(conn):
            schedule._put(conn, t, "2025-05-04", 1, "A", 1, None, None, "staff", True, "2027-05-04")
    with db.tx(conn):
        assert schedule._put(conn, t, "2027-05-03", 1, "A", 1, None, None, "staff", True, "2027-05-04")["changed"]


def test_same_id_with_a_different_name_warns(conn, org):
    t = org["t1"]
    schedule.set_entry(conn, t, "2027-05-04", "John Smith", 4242)
    r = schedule.set_entry(conn, t, "2027-05-05", "Jon Smyth", 4242)
    assert any("4242" in w for w in r["warnings"])


def test_no_id_and_no_pitch_source_warn_and_do_not_queue(conn, org):
    r = schedule.set_entry(conn, org["t1"], "2027-05-04", "No Id", None)
    assert r["warnings"] and conn.execute("SELECT build_state FROM starters WHERE id=?", (r["id"],)).fetchone()["build_state"] == ""
    conn.execute("UPDATE teams SET adapter='none' WHERE id=?", (org["t1"],))
    r = schedule.set_entry(conn, org["t1"], "2027-05-05", "Has Id", 5)
    assert any("no pitch source" in w for w in r["warnings"]) and conn.execute("SELECT build_state FROM starters WHERE id=?", (r["id"],)).fetchone()["build_state"] == ""


def test_a_valid_id_queues_a_build(conn, org):
    r = schedule.set_entry(conn, org["t1"], "2027-05-04", "Has Id", 5)
    assert conn.execute("SELECT build_state FROM starters WHERE id=?", (r["id"],)).fetchone()["build_state"] == "queued"


# ------------------------------------------------------------------ the grid saves all or nothing
def test_grid_all_or_nothing(conn, org):
    t = org["t1"]
    edits = [dict(team_id=t, game_date="2027-05-04", game_no=1, name="Good", id="1"), dict(team_id=t, game_date="2027-05-05", game_no=1, name="", id="2"),
             dict(team_id=t, game_date="2027-05-06", game_no=1, name="Bad Id", id="x9")]
    r = schedule.apply_grid(conn, edits, None, today="2027-05-03")
    assert r["saved"] == 0 and len(r["errors"]) == 2
    assert conn.execute("SELECT COUNT(*) n FROM starters").fetchone()["n"] == 0


def test_grid_window_error_rolls_back_the_valid_cells_too(conn, org):
    t = org["t1"]
    edits = [dict(team_id=t, game_date="2027-05-04", game_no=1, name="Good", id="1"), dict(team_id=t, game_date="2026-05-05", game_no=1, name="Wrong Year", id="2")]
    r = schedule.apply_grid(conn, edits, None, today="2027-05-03")
    assert r["saved"] == 0 and r["errors"] and conn.execute("SELECT COUNT(*) n FROM starters").fetchone()["n"] == 0


def test_grid_saves_clears_and_reports_unchanged(conn, org):
    t = org["t1"]
    schedule.set_entry(conn, t, "2027-05-04", "Keep", 1, "OppA")
    schedule.set_entry(conn, t, "2027-05-05", "Drop", 2)
    edits = [dict(team_id=t, game_date="2027-05-04", game_no=1, name="Keep", id="1", opp="OppA"), dict(team_id=t, game_date="2027-05-05", game_no=1, clear=True),
             dict(team_id=t, game_date="2027-05-06", game_no=1, name="New", id="3", opp="OppB")]
    r = schedule.apply_grid(conn, edits, None, today="2027-05-03")
    assert (r["saved"], r["unchanged"], r["cancelled"], r["errors"]) == (1, 1, 1, [])
    assert [x["pitcher_name"] for x in conn.execute("SELECT * FROM starters WHERE status='confirmed' ORDER BY game_date")] == ["Keep", "New"]


# ------------------------------------------------------------------ holds: rain delay and early finish
def test_rain_delay_hold_keeps_tonights_starter_then_expires_alone(conn, org, week):
    t, p = org["t1"], hitter(conn, org)
    schedule.hold_current_day(conn, t, "2027-05-04T23:30", "rain delay", None, now_iso=BEFORE)      # local 23:30 = 06:30Z May 5
    assert names(slate(conn, p, AT)) == ["Starter 04"]
    assert names(slate(conn, p, z("2027-05-05T06:29:59"))) == ["Starter 04"]
    assert names(slate(conn, p, z("2027-05-05T06:30:00"))) == ["Starter 05"]
    sd = schedule.slate_day(conn, t, AT)
    assert sd["source"] == "hold" and sd["valid_until"] == z("2027-05-05T06:30:00")


def test_hold_limits(conn, org, week):
    t = org["t1"]
    with pytest.raises(identity.EngineError, match="already past"):
        schedule.set_hold(conn, t, "2027-05-04", z("2027-05-04T18:00:00"), "", None, now_iso=NOON)
    with pytest.raises(identity.EngineError, match="at most 72"):
        schedule.set_hold(conn, t, "2027-05-04", z("2027-05-09T18:00:00"), "", None, now_iso=NOON)
    with pytest.raises(identity.EngineError):
        schedule.set_hold(conn, t, "not a date", z("2027-05-04T21:00:00"), "", None, now_iso=NOON)
    with pytest.raises(identity.EngineError):
        schedule.set_hold(conn, t, "2027-05-04", "tomorrow", "", None, now_iso=NOON)
    assert conn.execute("SELECT COUNT(*) n FROM slate_holds").fetchone()["n"] == 0


def test_a_hold_on_one_team_leaves_the_others_alone(conn, org, week):
    schedule.set_entry(conn, org["t2"], "2027-05-04", "Reno A", 1)
    schedule.set_entry(conn, org["t2"], "2027-05-05", "Reno B", 2)
    schedule.hold_current_day(conn, org["t1"], "2027-05-05T01:00", "", None, now_iso=BEFORE)
    assert names(slate(conn, hitter(conn, org), AT)) == ["Starter 04"]
    assert names(slate(conn, hitter(conn, org, "p3"), AT)) == ["Reno B"]


def test_newest_hold_wins_and_clear_restores_the_clock(conn, org, week):
    t, p = org["t1"], hitter(conn, org)
    schedule.hold_current_day(conn, t, "2027-05-05T01:00", "first", None, now_iso=BEFORE)
    schedule.set_hold(conn, t, "2027-05-05", z("2027-05-05T10:00:00"), "second", None, now_iso=BEFORE)
    assert names(slate(conn, p, AT)) == ["Starter 05"]
    assert conn.execute("SELECT COUNT(*) n FROM slate_holds WHERE cleared_at IS NULL").fetchone()["n"] == 1
    assert schedule.clear_hold(conn, t, None, now_iso=AT) and names(slate(conn, p, AT)) == ["Starter 05"]    # the clock agrees by then
    assert not schedule.clear_hold(conn, t, None)


def test_advance_shows_the_next_game_now_and_hands_back_to_the_clock(conn, org, week):
    t, p = org["t1"], hitter(conn, org)
    assert schedule.advance(conn, t, None, now_iso=NOON) == "2027-05-05"
    assert names(slate(conn, p, NOON)) == ["Starter 05"]
    assert names(slate(conn, p, z("2027-05-05T03:59:59"))) == ["Starter 05"]
    assert names(slate(conn, p, AT)) == ["Starter 05"]                                  # the clock reached it: same answer
    schedule.clear_hold(conn, t, None, now_iso=AT)
    assert names(slate(conn, p, AT)) == ["Starter 05"]
    with pytest.raises(identity.EngineError, match="Nothing is confirmed after"):
        schedule.advance(conn, org["t2"], None, now_iso=NOON)


# ------------------------------------------------------------------ people move
def test_promotion_shows_the_new_teams_starter_the_evening_before(conn, org):
    schedule.set_entry(conn, org["t1"], "2027-05-04", "Visalia Tue", 1)
    schedule.set_entry(conn, org["t1"], "2027-05-05", "Visalia Wed", 2)
    schedule.set_entry(conn, org["t2"], "2027-05-04", "Reno Tue", 3)
    schedule.set_entry(conn, org["t2"], "2027-05-05", "Reno Wed", 4)
    conn.execute("DELETE FROM assignments WHERE player_id=?", (org["p1"],))
    identity.assign(conn, org["p1"], org["t1"], "2027-01-01")
    identity.assign(conn, org["p1"], org["t2"], "2027-05-05")            # starts with Wednesday's game
    p = hitter(conn, org)
    assert names(slate(conn, p, NOON)) == ["Visalia Tue"]
    assert names(slate(conn, p, BEFORE)) == ["Visalia Tue"]
    assert names(slate(conn, p, AT)) == ["Reno Wed"]


def test_hitter_with_no_assignment_is_told_and_gets_nothing(conn, org):
    pid = identity.add_player(conn, "Free Agent", "R", None, "ORG-9")
    pl = slate(conn, conn.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone(), NOON)
    assert pl["packs"] == [] and "not assigned" in pl["notes"][0]


def test_a_brand_new_hitter_added_in_the_evening_sees_his_team_at_once(conn, org, week, tmp_path):
    bound(conn, tmp_path, org["t1"], week["2027-05-04"])
    pid = identity.add_player(conn, "New Guy", "L", org["t1"], "ORG-NEW", start="2027-05-05")          # the UTC date is already May 5 while it is still May 4 in California
    pl = slate(conn, conn.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone(), z("2027-05-05T02:00:00"))
    assert names(pl) == ["Starter 04"] and pl["packs"]


# ------------------------------------------------------------------ preview (the check you run on Monday)
def test_preview_matches_what_the_phones_get(conn, org, week, tmp_path):
    t = org["t1"]
    bound(conn, tmp_path, t, week["2027-05-04"], "L")                 # a left-side pack only: the right-handed hitter has nothing for his side
    out = schedule.preview(conn, [t], NOON)[0]
    kinds = {h["name"]: h["kind"] for h in out["hitters"]}
    assert kinds == {"Jordan Smith": "starter", "Alex Jones": "nothing"} and any("Alex Jones" in x for x in out["problems"])
    bound(conn, tmp_path, t, week["2027-05-04"], "R")
    assert {h["kind"] for h in schedule.preview(conn, [t], NOON)[0]["hitters"]} == {"starter"}
    assert conn.execute("SELECT COUNT(*) n FROM playlists").fetchone()["n"] == 0                # a preview writes nothing


def test_preview_flags_a_team_with_nothing_confirmed(conn, org):
    out = schedule.preview(conn, [org["t1"]], NOON)[0]
    assert out["entries"] == [] and "No starter is confirmed" in out["problems"][0]


# ------------------------------------------------------------------ a long random run keeps every promise
def test_random_operations_never_break_the_invariants(conn, org, tmp_path):
    rnd = random.Random(20270504)
    teams = [org["t1"], org["t2"]]
    built, did = {}, dict(set=0, cancel=0, hold=0, advance=0, clear=0)
    now = dt.datetime(2027, 5, 1, 12, tzinfo=dt.timezone.utc)
    for step in range(900):
        now += dt.timedelta(minutes=rnd.randint(1, 360))
        t, d = rnd.choice(teams), (now.date() + dt.timedelta(days=rnd.randint(-1, 11))).isoformat()
        op = rnd.random()
        try:
            if op < .35:
                r = schedule.set_entry(conn, t, d, f"P{rnd.randint(1, 9)}", rnd.choice([None, 11, 12, 13]), None, None, rnd.choice([1, 1, 1, 2]))
                did["set"] += 1
                if r["changed"] and rnd.random() < .6:
                    built[r["id"]] = [bound(conn, tmp_path, t, r["id"], s, tag=str(step)) for s in "LR"]
            elif op < .5:
                did["cancel"] += schedule.cancel_entry(conn, t, d, rnd.choice([1, 2]), None)
            elif op < .65:
                schedule.hold_current_day(conn, t, (now + dt.timedelta(hours=rnd.randint(1, 30))).astimezone(schedule.clock(conn, t)[0]).strftime("%Y-%m-%dT%H:%M"), "", None, schedule.to_iso(now))
                did["hold"] += 1
            elif op < .75:
                schedule.advance(conn, t, None, schedule.to_iso(now))
                did["advance"] += 1
            elif op < .8:
                did["clear"] += schedule.clear_hold(conn, t, None, schedule.to_iso(now))
        except identity.EngineError:
            pass
        iso = schedule.to_iso(now)
        for tid, who in ((org["t1"], "p1"), (org["t1"], "p2"), (org["t2"], "p3")):
            r = schedule.resolve(conn, tid, iso)
            es = r["entries"]
            assert len({e["game_date"] for e in es}) <= 1
            assert all(e["status"] == "confirmed" and e["team_id"] == tid and r["day"] <= e["game_date"] <= (dt.date.fromisoformat(r["day"]) + dt.timedelta(days=10)).isoformat() for e in es)
            assert [e["game_no"] for e in es] == sorted({e["game_no"] for e in es})
            assert r["valid_until"] > iso
            pl = playlist.compose(conn, hitter(conn, org, who), now_iso=iso, record=False)
            ok_ids = {e["id"] for e in es}
            for m in pl["packs"]:
                row = conn.execute("SELECT * FROM packs WHERE hash=?", (m["id"],)).fetchone()
                assert row["status"] == "active" and row["team_id"] == tid and (row["practice"] or row["starter_id"] is None or row["starter_id"] in ok_ids)
    assert all(v > 5 for v in did.values()), did            # the run really exercised every operation
