"""The schedule pages, button by button, and the whole path from an admin typing a starter to a hitter's phone showing it."""
import datetime as dt
import json
import re
import shutil
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from gameplan.engine import app as engine_app
from gameplan.engine import comps, db, identity, runner, schedule

from .test_answers_playlist import item

SECRET = "test-secret-not-for-production"
ADMIN = "admin-token-at-least-24-characters-long"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture
def env(tmp_path):
    app = engine_app.create_app(tmp_path / "data", SECRET, ADMIN, trust_proxy=False)
    c = db.connect(app.state.ctx.db_path)
    t1 = identity.add_team(c, "Visalia Rawhide", "Single-A", 516, 14, "tracking_drawn")
    t2 = identity.add_team(c, "Reno Aces", "Triple-A", 2310, 11, "tracking_drawn")
    t3 = identity.add_team(c, "Scottsdale Sandbox", "Rookie", None, None, "none")
    p1 = identity.add_player(c, "Jordan Smith", "L", t1, "ORG-1")
    p2 = identity.add_player(c, "Alex Jones", "R", t1, "ORG-2")
    p3 = identity.add_player(c, "Sam Lee", "R", t2, "ORG-3")
    coach_id, coach_tok = identity.create_staff(c, SECRET, "Coach V", "coach", [t1])
    yield dict(app=app, c=c, t1=t1, t2=t2, t3=t3, p1=p1, p2=p2, p3=p3, coach=coach_tok, tmp=tmp_path)
    c.close()


def login(env, token):
    cl = TestClient(env["app"], follow_redirects=False)
    r = cl.post("/staff/login", content=f"token={token}", headers=FORM)
    assert r.status_code == 303, r.text
    return cl


def csrf(cl, path="/staff/schedule"):
    return re.search(r'name="csrf" value="([0-9a-f]{32})"', cl.get(path).text).group(1)


def post(cl, path, token=None, **form):
    form = dict(form)
    if token is not None:
        form["csrf"] = token
    return cl.post(path, content=urlencode(form), headers=FORM)


def days(n=4):
    d0 = dt.date.fromisoformat(db.local_today())
    return [(d0 + dt.timedelta(days=i + 1)).isoformat() for i in range(n)]


def cell(team, date, game=1, name="", pid="", opp="", clear=False):
    k = f"{team}|{date}|{game}"
    out = {f"n_{k}": name, f"i_{k}": pid, f"o_{k}": opp}
    if clear:
        out[f"x_{k}"] = "1"
    return out


def fake_prepare(ok=True, no_pitches=False, calls=None, sims=None):
    """Stands in for gameplan.prepare: writes the same files and returns the same shape, with no network."""
    def prep(team_id, on, work, content, pitcher_id, n_starts, assess, sim=False):
        if calls is not None:
            calls.append(pitcher_id)
        if sims is not None:
            sims.append(sim)
        if no_pitches:
            return dict(ok=False, built=True, gates=[dict(gate="history", status="FAIL", detail="0 starts pooled", side=None)])
        content.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        for side in ("L", "R"):
            its = [item(f"s{pitcher_id}{side}{i}", strike=bool(i % 2), pt=["FF", "SL", "CH"][i % 3], stand=side) for i in range(4)]
            (content / f"queue_{side}.json").write_text(json.dumps(dict(packs=[dict(id=f"starter_{pitcher_id}_{side}", dir="x", title=f"Next starter: P{pitcher_id}", subtitle="Vs batters.", mode="train", items=its)])))
        (work / "private_keys.json").write_text("{}")
        return dict(ok=ok, built=True, gates=[] if ok else [dict(gate="playable_clips", status="FAIL", detail="0 clips", side="L")])
    return prep


# ------------------------------------------------------------------ access
def test_pages_need_login_and_a_coach_cannot_change_anything(env):
    anon = TestClient(env["app"], follow_redirects=False)
    for path in ("/staff/schedule", "/staff/schedule/preview", "/staff/comps?starter_id=1"):
        assert anon.get(path).status_code == 303
    coach = login(env, env["coach"])
    html = coach.get("/staff/schedule").text
    assert "Visalia Rawhide" in html and "Reno Aces" not in html and "readonly" in html and "Save the week" not in html
    tok = csrf(coach)
    d = days()[0]
    for path, form in (("/staff/schedule/save", cell(env["t1"], d, name="X", pid="1")), ("/staff/schedule/hold", dict(team_id=env["t1"], until="2099-01-01T00:00")),
                       ("/staff/schedule/advance", dict(team_id=env["t1"])), ("/staff/schedule/clearhold", dict(team_id=env["t1"]))):
        assert post(coach, path, tok, **form).status_code == 403, path
    assert env["c"].execute("SELECT COUNT(*) n FROM starters").fetchone()["n"] == 0


def test_save_needs_the_csrf_field(env):
    admin = login(env, ADMIN)
    assert post(admin, "/staff/schedule/save", None, **cell(env["t1"], days()[0], name="X", pid="1")).status_code == 403


# ------------------------------------------------------------------ the grid
def test_admin_fills_the_week_and_saving_again_changes_nothing(env):
    admin = login(env, ADMIN)
    tok, ds = csrf(admin), days()
    form = {}
    for d, nm, i in zip(ds, ["Ace One", "Ace Two", "Ace Three", "Ace Four"], ["101", "102", "103", "104"]):
        form.update(cell(env["t1"], d, name=nm, pid=i, opp="Modesto"))
    form.update(cell(env["t2"], ds[0], name="Reno Foe", pid="201", opp="Tacoma"))
    form["start"] = ds[0]
    r = post(admin, "/staff/schedule/save", tok, **form)
    assert r.status_code == 303 and "Saved+5" in r.headers["location"]
    rows = env["c"].execute("SELECT team_id, game_date, pitcher_name, pitcher_id, opponent, status, build_state FROM starters ORDER BY team_id, game_date").fetchall()
    assert len(rows) == 5 and all(x["status"] == "confirmed" and x["build_state"] == "queued" for x in rows)
    again = post(admin, "/staff/schedule/save", tok, **form)
    assert "Saved+0%2C+unchanged+5" in again.headers["location"]
    assert env["c"].execute("SELECT COUNT(*) n FROM starters").fetchone()["n"] == 5


def test_the_page_after_a_save_loads_with_its_message_and_the_same_week(env):
    admin = login(env, ADMIN)
    tok, ds = csrf(admin), days()
    r = post(admin, "/staff/schedule/save", tok, **cell(env["t1"], ds[1], name="Ace", pid="1"), start=ds[0])
    page = admin.get(r.headers["location"])
    assert page.status_code == 200 and "Saved 1" in page.text and f'value="Ace"' in page.text
    assert r.headers["location"].count("?") == 1 and f"start={ds[0]}" in r.headers["location"]
    again = post(admin, "/staff/schedule/save", tok, **cell(env["t1"], ds[1], name="Ace", pid="1"), start=ds[0])        # the form on that page saves again
    assert admin.get(again.headers["location"]).status_code == 200


def test_a_bad_box_saves_nothing_and_keeps_what_was_typed(env):
    admin = login(env, ADMIN)
    tok, ds = csrf(admin), days()
    form = {**cell(env["t1"], ds[0], name="Good Guy", pid="101"), **cell(env["t1"], ds[1], name="Bad Id", pid="12x"), **cell(env["t2"], ds[2], name="Wrong Year", pid="5"), "start": ds[0]}
    form[f"n_{env['t2']}|2019-05-04|1"] = "Old Year"
    form[f"i_{env['t2']}|2019-05-04|1"] = "9"
    r = post(admin, "/staff/schedule/save", tok, **form)
    assert r.status_code == 400 and "Nothing was saved" in r.text and "digits only" in r.text
    assert 'value="Good Guy"' in r.text and 'value="12x"' in r.text                 # nothing the user typed is lost
    assert env["c"].execute("SELECT COUNT(*) n FROM starters").fetchone()["n"] == 0


def test_wrong_year_is_caught_even_when_everything_else_is_fine(env):
    admin = login(env, ADMIN)
    tok = csrf(admin)
    r = post(admin, "/staff/schedule/save", tok, **{f"n_{env['t1']}|2019-05-04|1": "Old", f"i_{env['t1']}|2019-05-04|1": "9", "start": days()[0]})
    assert r.status_code == 400 and "outside the window" in r.text


def test_clear_and_replace_from_the_grid(env):
    admin = login(env, ADMIN)
    tok, ds = csrf(admin), days()
    post(admin, "/staff/schedule/save", tok, **cell(env["t1"], ds[0], name="Ace One", pid="101"), **cell(env["t1"], ds[1], name="Ace Two", pid="102"), start=ds[0])
    r = post(admin, "/staff/schedule/save", tok, **cell(env["t1"], ds[0], name="Replacement", pid="111"), **cell(env["t1"], ds[1], clear=True), start=ds[0])
    assert "Saved+1" in r.headers["location"] and "cleared+1" in r.headers["location"]
    live = [(x["game_date"], x["pitcher_name"]) for x in env["c"].execute("SELECT * FROM starters WHERE status='confirmed'")]
    assert live == [(ds[0], "Replacement")]
    assert {x["status"] for x in env["c"].execute("SELECT status FROM starters")} == {"confirmed", "superseded", "rejected"}


def test_a_blank_box_does_not_delete_an_existing_starter(env):
    admin = login(env, ADMIN)
    tok, ds = csrf(admin), days()
    post(admin, "/staff/schedule/save", tok, **cell(env["t1"], ds[0], name="Ace One", pid="101"), start=ds[0])
    post(admin, "/staff/schedule/save", tok, **cell(env["t1"], ds[0], name="", pid="", opp=""), start=ds[0])
    assert env["c"].execute("SELECT COUNT(*) n FROM starters WHERE status='confirmed'").fetchone()["n"] == 1


def test_html_in_a_name_is_escaped_everywhere(env):
    admin = login(env, ADMIN)
    tok, ds = csrf(admin), days()
    evil = '"><script>alert(1)</script>'
    post(admin, "/staff/schedule/save", tok, **cell(env["t1"], ds[0], name=evil, pid="1", opp=evil), start=ds[0])
    for path in ("/staff/schedule", "/staff/schedule/preview", "/staff/audit"):
        assert "<script>alert(1)" not in admin.get(path).text, path


def test_suggestions_show_and_saving_confirms_them(env):
    admin = login(env, ADMIN)
    d = days()[0]
    env["c"].execute("INSERT INTO starters(team_id, game_date, pitcher_id, pitcher_name, status, source) VALUES (?,?,?,?,?,?)", (env["t1"], d, 77, "Probable Pete", "suggested", "schedule"))
    html = admin.get(f"/staff/schedule?start={d}").text
    assert 'value="Probable Pete"' in html and "suggested by the MLB schedule" in html
    tok = csrf(admin)
    post(admin, "/staff/schedule/save", tok, **cell(env["t1"], d, name="Probable Pete", pid="77"), start=d)
    assert [x["status"] for x in env["c"].execute("SELECT status FROM starters ORDER BY id")] == ["superseded", "confirmed"]


def test_week_navigation_validates_the_date(env):
    admin = login(env, ADMIN)
    assert admin.get("/staff/schedule?start=2027-05-04").status_code == 200
    assert admin.get("/staff/schedule?start=banana").status_code == 400


# ------------------------------------------------------------------ the hold buttons
def test_hold_advance_and_clear_buttons(env):
    admin = login(env, ADMIN)
    tok, ds = csrf(admin), days(3)
    d0 = db.local_today()
    for d, n in zip([d0] + ds, ["Tonight", "Tomorrow", "After", "Later"]):
        schedule.set_entry(env["c"], env["t1"], d, n, 1)
    from zoneinfo import ZoneInfo
    pac = lambda h: (dt.datetime.now(ZoneInfo("America/Los_Angeles")) + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M")      # the form takes the team's local clock
    soon = pac(2)
    r = post(admin, "/staff/schedule/hold", tok, team_id=env["t1"], until=soon, reason="rain delay")
    assert r.status_code == 303 and "Held" in r.headers["location"]
    assert "rain delay" in admin.get("/staff/schedule").text and "Back to the clock" in admin.get("/staff/schedule").text
    assert post(admin, "/staff/schedule/clearhold", tok, team_id=env["t1"]).status_code == 303
    assert env["c"].execute("SELECT COUNT(*) n FROM slate_holds WHERE cleared_at IS NULL").fetchone()["n"] == 0
    past = pac(-1)
    assert post(admin, "/staff/schedule/hold", tok, team_id=env["t1"], until=past).status_code == 400
    assert post(admin, "/staff/schedule/hold", tok, team_id=env["t1"], until="garbage").status_code == 400
    assert post(admin, "/staff/schedule/advance", tok, team_id=env["t2"]).status_code == 409


def test_a_hold_cannot_cross_to_a_team_outside_scope_or_that_does_not_exist(env):
    admin = login(env, ADMIN)
    tok = csrf(admin)
    assert post(admin, "/staff/schedule/hold", tok, team_id=9999, until="2099-01-01T00:00").status_code == 403


# ------------------------------------------------------------------ builds
def test_build_queue_registers_packs_for_the_right_game_only(env):
    c, ds = env["c"], days(2)
    a = schedule.set_entry(c, env["t1"], ds[0], "Ace One", 101)["id"]
    b = schedule.set_entry(c, env["t1"], ds[1], "Ace Two", 102)["id"]
    data = env["app"].state.ctx.data_dir
    done = runner.build_queued(env["app"].state.ctx.db_path, data, fake_prepare(), limit=5)
    assert done == [a, b]
    for sid, pid in ((a, 101), (b, 102)):
        rows = c.execute("SELECT * FROM packs WHERE starter_id=? AND status='active'", (sid,)).fetchall()
        assert {r["side"] for r in rows} == {"L", "R"} and all(f"P{pid}" in r["title"] for r in rows)
        assert c.execute("SELECT build_state FROM starters WHERE id=?", (sid,)).fetchone()["build_state"] == "ready"
    assert schedule.content_state(c, a) == "ready"
    runner.build_queued(env["app"].state.ctx.db_path, data, fake_prepare(), limit=5)               # nothing queued any more: nothing happens
    assert c.execute("SELECT COUNT(*) n FROM packs").fetchone()["n"] == 4


def test_building_one_day_never_retires_another_days_packs(env):
    c, ds = env["c"], days(2)
    a = schedule.set_entry(c, env["t1"], ds[0], "Ace One", 101)["id"]
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare())
    b = schedule.set_entry(c, env["t1"], ds[1], "Ace Two", 102)["id"]
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare())
    assert c.execute("SELECT COUNT(*) n FROM packs WHERE starter_id=? AND status='active'", (a,)).fetchone()["n"] == 2
    assert c.execute("SELECT COUNT(*) n FROM packs WHERE starter_id=? AND status='active'", (b,)).fetchone()["n"] == 2


def test_no_video_is_reported_and_leaves_the_game_without_packs(env):
    c = env["c"]
    a = schedule.set_entry(c, env["t1"], days()[0], "Milb Arm", 555)["id"]
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(no_pitches=True))
    row = c.execute("SELECT * FROM starters WHERE id=?", (a,)).fetchone()
    assert row["build_state"] == "no_video" and "history" in row["build_detail"] and schedule.content_state(c, a) == "none"
    admin = login(env, ADMIN)
    assert "no video or tracking found" in admin.get(f"/staff/schedule?start={days()[0]}").text and "find a comp" in admin.get(f"/staff/schedule?start={days()[0]}").text


def test_a_failed_or_crashed_build_is_visible_and_retryable(env):
    c = env["c"]
    a = schedule.set_entry(c, env["t1"], days()[0], "Ace", 7)["id"]
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(ok=False))
    assert c.execute("SELECT build_state FROM starters WHERE id=?", (a,)).fetchone()["build_state"] == "failed"
    admin = login(env, ADMIN)
    tok = csrf(admin)
    assert post(admin, "/staff/starters/retry", tok, starter_id=a).status_code == 303
    assert c.execute("SELECT build_state FROM starters WHERE id=?", (a,)).fetchone()["build_state"] == "queued"
    def boom(*x, **k):
        raise RuntimeError("savant down")
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, boom)
    r = c.execute("SELECT * FROM starters WHERE id=?", (a,)).fetchone()
    assert r["build_state"] == "failed" and "savant down" in r["build_detail"]


def test_a_build_left_building_by_a_restart_is_marked_failed_not_stuck(env):
    c = env["c"]
    a = schedule.set_entry(c, env["t1"], days()[0], "Ace", 7)["id"]
    c.execute("UPDATE starters SET build_state='building', build_at=? WHERE id=?", (db.plus(db.now(), hours=-2), a))
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare())
    assert c.execute("SELECT build_state FROM starters WHERE id=?", (a,)).fetchone()["build_state"] == "failed"


def test_replacing_a_starter_after_his_pitches_were_built_retires_them_and_rebuilds(env):
    c, d = env["c"], days()[0]
    a = schedule.set_entry(c, env["t1"], d, "Scratched", 101)["id"]
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare())
    b = schedule.set_entry(c, env["t1"], d, "Replacement", 202)["id"]
    assert c.execute("SELECT COUNT(*) n FROM packs WHERE starter_id=? AND status='active'", (a,)).fetchone()["n"] == 0
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare())
    assert c.execute("SELECT COUNT(*) n FROM packs WHERE starter_id=? AND status='active'", (b,)).fetchone()["n"] == 2


# ------------------------------------------------------------------ preview
def test_preview_page_lists_the_problems_before_the_night_not_after(env):
    admin = login(env, ADMIN)
    html = admin.get("/staff/schedule/preview").text
    assert "no starter confirmed" in html and "Jordan Smith" in html
    sd = schedule.slate_day(env["c"], env["t1"])["date"]
    nxt = (dt.date.fromisoformat(sd) + dt.timedelta(days=1)).isoformat()
    schedule.set_entry(env["c"], env["t1"], sd, "Tonight Ace", 5)
    schedule.set_entry(env["c"], env["t1"], nxt, "Tomorrow Ace", 6)
    assert "pitches are none" in admin.get("/staff/schedule/preview").text
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(), limit=5)
    now_html, next_html = admin.get("/staff/schedule/preview").text, admin.get("/staff/schedule/preview?when=next").text
    assert "Tonight Ace" in now_html and "Tomorrow Ace" not in now_html and "Tomorrow Ace" in next_html
    assert "hitters will see the starter" in now_html and "hitters will see the starter" in next_html
    coach = login(env, env["coach"])
    assert "Reno Aces" not in coach.get("/staff/schedule/preview").text


# ------------------------------------------------------------------ comps
PROFILE = dict(hand="R", rel_z="5.9", rel_x="2.0", ext="6.3", arm_angle="35", t1="FF", u1="55", v1="93", h1="8", i1="16", t2="SL", u2="25", v2="85", h2="3", i2="2", t3="CH", u3="20", v3="86", h3="14", i3="6")


def test_comp_search_ranks_and_use_queues_a_rebuild_labelled_as_a_comp(env):
    c = env["c"]
    a = schedule.set_entry(c, env["t1"], days()[0], "Milb Arm", 555)["id"]
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(no_pitches=True))
    admin = login(env, ADMIN)
    tok = csrf(admin)
    r = post(admin, "/staff/comps/search", tok, starter_id=a, **PROFILE)
    assert r.status_code == 200 and "Closest MLB pitchers" in r.text
    comp_id = re.search(r'name="comp_id" value="(\d+)"', r.text).group(1)
    pool = comps.load_pool()
    comp = next(p for p in pool["pitchers"] if str(p["id"]) == comp_id)
    assert comp["hand"] == "R"
    u = post(admin, "/staff/comps/use", tok, starter_id=a, comp_id=comp_id, profile="{}")
    assert u.status_code == 303
    row = c.execute("SELECT * FROM starters WHERE id=?", (a,)).fetchone()
    assert (row["content_kind"], row["content_pitcher_id"], row["comp_note"], row["build_state"]) == ("comp", comp["id"], comp["name"], "queued")
    calls = []
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(calls=calls))
    assert calls == [comp["id"]]                                                       # the build used the comp's pitches, not the starter's id
    titles = {x["title"] for x in c.execute("SELECT title FROM packs WHERE starter_id=? AND status='active'", (a,))}
    assert titles == {f"Comp for Milb Arm: {comp['name']}"}                            # a hitter can never mistake it for the real starter
    assert "comp:" in admin.get(f"/staff/schedule?start={days()[0]}").text
    assert c.execute("SELECT COUNT(*) n FROM audit_log WHERE action='comp_chosen'").fetchone()["n"] == 1


def test_comp_clear_goes_back_to_his_own_and_a_coach_cannot_choose(env):
    c = env["c"]
    a = schedule.set_entry(c, env["t1"], days()[0], "Milb Arm", 555)["id"]
    pid = comps.load_pool()["pitchers"][0]["id"]
    coach = login(env, env["coach"])
    assert post(coach, "/staff/comps/use", csrf(coach), starter_id=a, comp_id=pid).status_code == 403
    admin = login(env, ADMIN)
    tok = csrf(admin)
    post(admin, "/staff/comps/use", tok, starter_id=a, comp_id=pid)
    post(admin, "/staff/comps/clear", tok, starter_id=a)
    r = c.execute("SELECT * FROM starters WHERE id=?", (a,)).fetchone()
    assert (r["content_kind"], r["content_pitcher_id"], r["build_state"]) == ("own", None, "queued")


def test_comp_use_rejects_an_unknown_pitcher_and_offers_comps_where_there_is_no_source(env):
    admin = login(env, ADMIN)
    tok = csrf(admin)
    a = schedule.set_entry(env["c"], env["t1"], days()[0], "X", 5)["id"]
    assert post(admin, "/staff/comps/use", tok, starter_id=a, comp_id=1).status_code == 400
    z = schedule.set_entry(env["c"], env["t3"], days()[0], "Y", 6)["id"]
    assert "no pitch source" in admin.get(f"/staff/schedule?start={days()[0]}").text and "find a comp" in admin.get(f"/staff/schedule?start={days()[0]}").text


def test_comp_search_errors_are_plain(env):
    a = schedule.set_entry(env["c"], env["t1"], days()[0], "X", 5)["id"]
    admin = login(env, ADMIN)
    tok = csrf(admin)
    assert "Pick the throwing hand" in post(admin, "/staff/comps/search", tok, starter_id=a, hand="").text
    assert "Add at least one pitch" in post(admin, "/staff/comps/search", tok, starter_id=a, hand="R").text
    assert "No usable pitches" in post(admin, "/staff/comps/search", tok, starter_id=a, csv="a,b\n1,2\n").text
    assert post(admin, "/staff/comps/search", tok, starter_id=999, hand="R").status_code == 404


def test_comp_search_accepts_a_trackman_style_export(env):
    a = schedule.set_entry(env["c"], env["t1"], days()[0], "X", 5)["id"]
    lines = ["PitcherThrows,TaggedPitchType,RelSpeed,RelHeight,RelSide,Extension,HorzBreak,InducedVertBreak"]
    for i in range(120):
        lines.append("Right,Fastball,%0.1f,5.9,-2.0,6.3,%0.1f,%0.1f" % (92 + (i % 5) * .4, 8 + (i % 3), 16 + (i % 4)))
    for i in range(60):
        lines.append("Right,Slider,%0.1f,5.9,-2.0,6.3,%0.1f,%0.1f" % (84 + (i % 4) * .5, -3 - (i % 3), 2 + (i % 3)))
    admin = login(env, ADMIN)
    r = post(admin, "/staff/comps/search", csrf(admin), starter_id=a, csv="\n".join(lines))
    assert r.status_code == 200 and "Closest MLB pitchers" in r.text and "No arm angle in the file" in r.text


# ------------------------------------------------------------------ the whole path
def test_admin_types_a_week_and_a_hitter_sees_the_right_starter_on_the_right_night(env):
    c = env["c"]
    admin = login(env, ADMIN)
    tok = csrf(admin)
    sd = schedule.slate_day(c, env["t1"])["date"]                       # what the clock shows hitters right now
    nxt = (dt.date.fromisoformat(sd) + dt.timedelta(days=1)).isoformat()
    post(admin, "/staff/schedule/save", tok, **cell(env["t1"], sd, name="Tonight Ace", pid="101", opp="Modesto"), **cell(env["t1"], nxt, name="Tomorrow Ace", pid="102", opp="Modesto"),
         **cell(env["t2"], sd, name="Reno Ace", pid="201", opp="Tacoma"), start=sd)
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(), limit=10)
    shutil.copytree(env["app"].state.ctx.data_dir / "content", env["app"].state.ctx.content_root, dirs_exist_ok=True) if (env["app"].state.ctx.data_dir / "content") != env["app"].state.ctx.content_root else None
    phone = TestClient(env["app"])
    tk = identity.create_claim(c, SECRET, env["p1"])
    cred = phone.post("/api/claim/confirm", json={"token": tk, "label": "x"}).json()["credential"]
    pl = phone.get("/api/playlist", headers={"Authorization": f"Bearer {cred}"}).json()
    assert [g["starter"] for g in pl["slate"]["games"]] == ["Tonight Ace"] and pl["slate"]["games"][0]["opponent"] == "Modesto"
    assert pl["packs"] and all("P101" in p["title"] for p in pl["packs"] if p["mode"] == "train") and pl["slate"]["valid_until"] > db.now()
    tk2 = identity.create_claim(c, SECRET, env["p3"])
    cred2 = phone.post("/api/claim/confirm", json={"token": tk2, "label": "y"}).json()["credential"]
    pl2 = phone.get("/api/playlist", headers={"Authorization": f"Bearer {cred2}"}).json()
    assert [g["starter"] for g in pl2["slate"]["games"]] == ["Reno Ace"] and all("P201" in p["title"] for p in pl2["packs"])
    # an admin advances Visalia only: its hitters move on, Reno's do not
    assert post(admin, "/staff/schedule/advance", tok, team_id=env["t1"]).status_code == 303
    pl = phone.get("/api/playlist", headers={"Authorization": f"Bearer {cred}"}).json()
    assert [g["starter"] for g in pl["slate"]["games"]] == ["Tomorrow Ace"] and pl["slate"]["source"] == "hold" and all("P102" in p["title"] for p in pl["packs"] if p["mode"] == "train")
    pl2 = phone.get("/api/playlist", headers={"Authorization": f"Bearer {cred2}"}).json()
    assert [g["starter"] for g in pl2["slate"]["games"]] == ["Reno Ace"] and pl2["slate"]["source"] == "clock"
    assert post(admin, "/staff/schedule/clearhold", tok, team_id=env["t1"]).status_code == 303
    pl = phone.get("/api/playlist", headers={"Authorization": f"Bearer {cred}"}).json()
    assert [g["starter"] for g in pl["slate"]["games"]] == ["Tonight Ace"]


def test_today_page_lists_schedule_trouble_and_clears_when_fixed(env):
    admin = login(env, ADMIN)
    assert "no starter is confirmed" in admin.get("/staff").text
    sd = schedule.slate_day(env["c"], env["t1"])["date"]
    a = schedule.set_entry(env["c"], env["t1"], sd, "Ace", None)["id"]
    assert "has no player id" in admin.get("/staff").text
    schedule.set_entry(env["c"], env["t1"], sd, "Ace", 7)
    schedule.set_entry(env["c"], env["t2"], sd, "Reno Ace", 8)
    assert "not ready" in admin.get("/staff").text
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(no_pitches=True), limit=5)
    html = admin.get("/staff").text
    assert "could not be found" in html and "Find a comp or retry" in html
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(), limit=5)
    schedule.cancel_entry(env["c"], env["t3"], sd, 1, None)
    row = env["c"].execute("SELECT id FROM starters WHERE pitcher_name='Ace' AND status='confirmed'").fetchone()
    env["c"].execute("UPDATE starters SET build_state='queued' WHERE id=?", (row["id"],))
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(), limit=5)
    coach = login(env, env["coach"])
    assert "Reno" not in coach.get("/staff").text                                                # a coach is told only about their own affiliate


def test_a_comp_is_cut_from_the_mlb_pitchers_real_video_even_for_a_drawn_pitch_affiliate_or_one_with_no_source(env):
    c, ds = env["c"], days(2)
    pid = comps.load_pool()["pitchers"][0]["id"]
    admin = login(env, ADMIN)
    tok = csrf(admin)
    for team, d in ((env["t1"], ds[0]), (env["t3"], ds[1])):                              # Visalia draws its own pitches; Scottsdale has no pitch source at all
        sid = schedule.set_entry(c, team, d, "Milb Arm", 555)["id"]
        assert post(admin, "/staff/comps/use", tok, starter_id=sid, comp_id=pid).status_code == 303
        sims = []
        runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, fake_prepare(sims=sims), limit=5)
        assert sims == [False], team                                                     # video, not a drawn pitch
        assert {r["adapter"] for r in c.execute("SELECT adapter FROM packs WHERE starter_id=?", (sid,))} == {"mlb_video"}
        assert schedule.content_state(c, sid) == "ready"


# ------------------------------------------------------------------ uploading his own pitches
FIXTURE = (__import__("pathlib").Path(__file__).parent / "fixtures" / "statcast_rhp.csv").read_text()


def test_upload_preview_then_save_queues_every_game_of_that_pitcher(env):
    c, ds = env["c"], days(3)
    a = schedule.set_entry(c, env["t1"], ds[0], "Milb Arm", 434378)["id"]
    b = schedule.set_entry(c, env["t1"], ds[2], "Milb Arm", 434378)["id"]
    other = schedule.set_entry(c, env["t1"], ds[1], "Someone Else", 5)["id"]
    c.execute("UPDATE starters SET build_state='no_video' WHERE id IN (?,?)", (a, b))
    c.execute("UPDATE starters SET build_state='ready' WHERE id=?", (other,))
    admin = login(env, ADMIN)
    tok = csrf(admin)
    assert "upload his pitches or find a comp" in admin.get(f"/staff/schedule?start={ds[0]}").text
    assert "Upload his pitches" in admin.get(f"/staff/import?starter_id={a}").text
    pv = post(admin, "/staff/import/preview", tok, starter_id=a, csv=FIXTURE, plate_sign="1")
    assert pv.status_code == 200 and "rows can be drawn" in pv.text and "Use these pitches" in pv.text and "% of the pitches are in the strike zone" in pv.text and "<td>FF</td>" in pv.text
    assert c.execute("SELECT COUNT(*) n FROM pitch_imports").fetchone()["n"] == 0                      # a preview stores nothing
    sv = post(admin, "/staff/import/save", tok, starter_id=a, csv=FIXTURE, plate_sign="1", note="TruMedia, last 3 starts")
    assert sv.status_code == 303 and "2+game" in sv.headers["location"]
    imp = pitchimport_load(c, 434378)
    assert imp["note"] == "TruMedia, last 3 starts" and len(imp["rows"]) > 250
    states = {r["id"]: r["build_state"] for r in c.execute("SELECT id, build_state FROM starters")}
    assert states[a] == states[b] == "queued" and states[other] == "ready"                                    # only this pitcher's games are requeued by the upload
    assert c.execute("SELECT COUNT(*) n FROM audit_log WHERE action='pitches_imported'").fetchone()["n"] == 1
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, limit=5)               # the real pipeline, from the upload
    for sid in (a, b):
        r = c.execute("SELECT * FROM starters WHERE id=?", (sid,)).fetchone()
        assert r["build_state"] == "ready" and "uploaded tracking" in r["build_detail"], (r["build_state"], r["build_detail"])


def pitchimport_load(c, pid):
    from gameplan.engine import pitchimport
    return pitchimport.load(c, pid)


def test_a_bad_file_is_explained_and_saves_nothing(env):
    a = schedule.set_entry(env["c"], env["t1"], days()[0], "Milb Arm", 434378)["id"]
    admin = login(env, ADMIN)
    tok = csrf(admin)
    r = post(admin, "/staff/import/preview", tok, starter_id=a, csv="a,b\n1,2\n")
    assert r.status_code == 200 and "The file is missing" in r.text and "Use these pitches" not in r.text
    assert post(admin, "/staff/import/save", tok, starter_id=a, csv="a,b\n1,2\n").status_code == 400
    assert env["c"].execute("SELECT COUNT(*) n FROM pitch_imports").fetchone()["n"] == 0


def test_upload_needs_a_player_id_and_an_admin_to_save(env):
    c = env["c"]
    noid = schedule.set_entry(c, env["t1"], days()[0], "No Id", None)["id"]
    a = schedule.set_entry(c, env["t1"], days()[1], "Milb Arm", 434378)["id"]
    admin = login(env, ADMIN)
    tok = csrf(admin)
    assert post(admin, "/staff/import/preview", tok, starter_id=noid, csv=FIXTURE).status_code == 409
    coach = login(env, env["coach"])
    ct = csrf(coach)
    assert post(coach, "/staff/import/preview", ct, starter_id=a, csv=FIXTURE).status_code == 200      # a coach may look
    assert post(coach, "/staff/import/save", ct, starter_id=a, csv=FIXTURE).status_code == 403          # but not change
    assert post(admin, "/staff/import/save", None, starter_id=a, csv=FIXTURE).status_code == 403        # and CSRF is required
    assert c.execute("SELECT COUNT(*) n FROM pitch_imports").fetchone()["n"] == 0


def test_a_scoped_coach_cannot_reach_another_affiliates_game(env):
    other = schedule.set_entry(env["c"], env["t2"], days()[0], "Reno Arm", 7)["id"]
    coach = login(env, env["coach"])
    assert coach.get(f"/staff/import?starter_id={other}").status_code == 404
    assert post(coach, "/staff/import/preview", csrf(coach), starter_id=other, csv=FIXTURE).status_code == 404


def test_uploaded_pitches_reach_the_hitters_phone_as_drawn_pitches(env):
    c = env["c"]
    sd = schedule.slate_day(c, env["t1"])["date"]
    sid = schedule.set_entry(c, env["t1"], sd, "Milb Arm", 434378, "Modesto")["id"]
    admin = login(env, ADMIN)
    tok = csrf(admin)
    post(admin, "/staff/import/save", tok, starter_id=sid, csv=FIXTURE)
    runner.build_queued(env["app"].state.ctx.db_path, env["app"].state.ctx.data_dir, limit=2)
    phone = TestClient(env["app"])
    cred = phone.post("/api/claim/confirm", json={"token": identity.create_claim(c, SECRET, env["p1"]), "label": "x"}).json()["credential"]
    pl = phone.get("/api/playlist", headers={"Authorization": f"Bearer {cred}"}).json()
    train = [p for p in pl["packs"] if p["mode"] == "train"]
    assert train and train[0]["title"].startswith("Next starter") and all(i["sim"] and i["file"] is None for p in train for i in p["items"])
    assert [g["starter"] for g in pl["slate"]["games"]] == ["Milb Arm"]
