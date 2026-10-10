import re

import pytest
from fastapi.testclient import TestClient

from gameplan.engine import app as engine_app
from gameplan.engine import db, identity, runner

from .test_answers_playlist import ans, make_pack

SECRET = "test-secret-not-for-production"
ADMIN = "admin-token-at-least-24-characters-long"


@pytest.fixture
def env(tmp_path):
    app = engine_app.create_app(tmp_path / "data", SECRET, ADMIN, trust_proxy=False)
    c = db.connect(app.state.ctx.db_path)
    t1 = identity.add_team(c, "Visalia Rawhide", "Single-A", 516, 14, "tracking_drawn")
    t2 = identity.add_team(c, "Reno Aces", "Triple-A", 2310, 11, "tracking_drawn")
    p1 = identity.add_player(c, "Jordan Smith", "L", t1, "ORG-1")
    p2 = identity.add_player(c, "Alex Jones", "R", t1, "ORG-2")
    p3 = identity.add_player(c, "Sam Lee", "R", t2, "ORG-3")
    coach_id, coach_tok = identity.create_staff(c, SECRET, "Coach V", "coach", [t1])
    h = make_pack(c, tmp_path / "work", team=t1)
    import shutil
    shutil.copytree(tmp_path / "work" / "content", app.state.ctx.content_root, dirs_exist_ok=True)
    yield dict(app=app, c=c, t1=t1, t2=t2, p1=p1, p2=p2, p3=p3, coach=coach_tok, pack=h, tmp=tmp_path)
    c.close()


def login(env, token):
    cl = TestClient(env["app"], follow_redirects=False)
    r = cl.post("/staff/login", content=f"token={token}", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 303, r.text
    return cl


def csrf(cl, path="/staff/roster"):
    return re.search(r'name="csrf" value="([0-9a-f]{32})"', cl.get(path).text).group(1)


def post(cl, path, **form):
    from urllib.parse import urlencode
    return cl.post(path, content=urlencode(form), headers={"Content-Type": "application/x-www-form-urlencoded"})


def test_pages_need_a_login_and_a_bad_token_is_refused_and_audited(env):
    cl = TestClient(env["app"], follow_redirects=False)
    for path in ("/staff", "/staff/roster", "/staff/starters", "/staff/packs", "/staff/settings", "/staff/leaderboard", "/staff/export.csv", "/staff/admin", "/staff/audit", f"/staff/player/{env['p1']}"):
        r = cl.get(path)
        assert r.status_code == 303 and r.headers["location"] == "/staff/login", path
    bad = post(cl, "/staff/login", token="nope")
    assert bad.status_code == 401 and "not valid" in bad.text
    assert env["c"].execute("SELECT COUNT(*) n FROM audit_log WHERE action='staff_login_failed'").fetchone()["n"] == 1


def test_cookie_is_httponly_samesite_strict(env):
    cl = TestClient(env["app"], follow_redirects=False)
    r = post(cl, "/staff/login", token=ADMIN)
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=strict" in sc


def test_every_page_renders_for_the_admin(env):
    cl = login(env, ADMIN)
    for path in ("/staff", "/staff/roster", "/staff/starters", "/staff/packs", "/staff/settings", "/staff/leaderboard", "/staff/admin", "/staff/audit", f"/staff/player/{env['p1']}", "/staff/export.csv"):
        r = cl.get(path)
        assert r.status_code == 200, (path, r.status_code)


def test_forms_without_the_csrf_field_are_refused_and_nothing_changes(env):
    cl = login(env, ADMIN)
    r = post(cl, f"/staff/player/{env['p1']}/claim")
    assert r.status_code == 403 and "expired" in r.json()["error"]
    assert env["c"].execute("SELECT COUNT(*) n FROM claim_tokens").fetchone()["n"] == 0
    r = post(cl, f"/staff/player/{env['p1']}/claim", csrf="0" * 32)
    assert r.status_code == 403


def test_claim_link_page_shows_a_working_link_and_qr_and_it_signs_a_hitter_in(env):
    cl = login(env, ADMIN)
    r = post(cl, f"/staff/player/{env['p1']}/claim", csrf=csrf(cl))
    assert r.status_code == 200 and "<svg" in r.text
    url = re.search(r"http://testserver/c/([A-Za-z0-9_-]+)", r.text)
    assert url
    player = TestClient(env["app"])
    conf = player.post("/api/claim/confirm", json={"token": url.group(1), "label": "t"})
    assert conf.status_code == 200 and conf.json()["player"]["name"] == "Jordan Smith"


def test_recovery_code_page_and_redeem(env):
    cl = login(env, ADMIN)
    r = post(cl, f"/staff/player/{env['p2']}/recovery", csrf=csrf(cl))
    code = re.search(r'class="code">(\d{4}) (\d{4})', r.text)
    assert code
    got = TestClient(env["app"]).post("/api/recover", json={"code": code.group(1) + code.group(2), "label": "t"})
    assert got.status_code == 200 and got.json()["player"]["name"] == "Alex Jones"


def test_a_coach_sees_only_his_teams_hitters_everywhere(env):
    cl = login(env, env["coach"])
    roster = cl.get("/staff/roster").text
    assert "Jordan Smith" in roster and "Sam Lee" not in roster and "Reno Aces" not in roster.split("<h2>Add a hitter")[1].split("</select>")[0]
    assert cl.get(f"/staff/player/{env['p3']}").status_code == 404
    assert post(cl, f"/staff/player/{env['p3']}/claim", csrf=csrf(cl)).status_code == 404
    assert post(cl, f"/staff/player/{env['p3']}/recovery", csrf=csrf(cl)).status_code == 404
    assert cl.get(f"/staff/leaderboard?team_id={env['t2']}").status_code == 403
    assert cl.get(f"/staff/export.csv?team_id={env['t2']}").status_code == 403
    assert post(cl, "/staff/settings", csrf=csrf(cl), team_id=env["t2"], pause_ms=100, view="low_home", daily_cap=20, ask="both", reveal="1", assess_every_days=28).status_code == 403
    assert post(cl, "/staff/starters/confirm", csrf=csrf(cl), team_id=env["t2"], game_date="2026-10-20", pitcher_name="X", pitcher_id="1").status_code == 403
    assert post(cl, "/staff/roster/add", csrf=csrf(cl), name="Intruder", bats="R", team_id=env["t2"]).status_code == 403
    for admin_only in ("/staff/admin", "/staff/audit"):
        assert cl.get(admin_only).status_code == 403


def test_a_coach_cannot_remove_another_teams_phone_or_retire_another_teams_pack(env, tmp_path):
    c = env["c"]
    tok = identity.create_claim(c, SECRET, env["p3"])
    identity.claim_confirm(c, SECRET, tok, "x")
    cid = c.execute("SELECT id FROM credentials WHERE player_id=?", (env["p3"],)).fetchone()["id"]
    other = make_pack(c, tmp_path / "w2", team=env["t2"], pk_id="o")
    cl = login(env, env["coach"])
    assert post(cl, f"/staff/credential/{cid}/revoke", csrf=csrf(cl)).status_code == 404
    assert post(cl, f"/staff/packs/{other}/retire", csrf=csrf(cl)).status_code == 404
    assert c.execute("SELECT revoked_at FROM credentials WHERE id=?", (cid,)).fetchone()["revoked_at"] is None
    assert c.execute("SELECT status FROM packs WHERE hash=?", (other,)).fetchone()["status"] == "active"


def test_roster_import_and_add_work_and_report_bad_rows(env):
    cl = login(env, ADMIN)
    csvtext = "name,bats,team,org_id\nNew Guy,R,Visalia Rawhide,ORG-9\nBad Row,Q,Visalia Rawhide,ORG-10\n"
    r = post(cl, "/staff/roster/import", csrf=csrf(cl), csv=csvtext)
    assert r.status_code == 303 and "Added 1" in r.headers["location"].replace("+", " ") and "skipped" in r.headers["location"]
    assert env["c"].execute("SELECT COUNT(*) n FROM players WHERE org_id='ORG-9'").fetchone()["n"] == 1
    post(cl, "/staff/roster/add", csrf=csrf(cl), name="Added Here", bats="L", team_id=env["t1"], org_id="ORG-11")
    assert env["c"].execute("SELECT COUNT(*) n FROM players WHERE org_id='ORG-11'").fetchone()["n"] == 1


def test_settings_validate_and_change_what_the_phone_receives(env):
    cl = login(env, ADMIN)
    r = post(cl, "/staff/settings", csrf=csrf(cl), team_id=env["t1"], pause_ms=500, view="low_home", daily_cap=20, ask="both", reveal="1", assess_every_days=28)
    assert r.status_code == 400
    r = post(cl, "/staff/settings", csrf=csrf(cl), team_id=env["t1"], pause_ms=300, view="hitter_eye", daily_cap=20, ask="both", reveal="1", assess_every_days=28)
    assert r.status_code == 400 and "250" in r.json()["error"]
    r = post(cl, "/staff/settings", csrf=csrf(cl), team_id=env["t1"], pause_ms=220, view="low_home", daily_cap=12, ask="zone", reveal="0", assess_every_days=14)
    assert r.status_code == 303
    tok = identity.create_claim(env["c"], SECRET, env["p1"])
    cred = TestClient(env["app"]).post("/api/claim/confirm", json={"token": tok}).json()["credential"]
    me = TestClient(env["app"]).get("/api/me", headers={"Authorization": f"Bearer {cred}"}).json()
    assert me["settings"] == dict(pause_ms=220, view="low_home", daily_cap=12, ask="zone", reveal=False, assess_every_days=14)
    assert env["c"].execute("SELECT COUNT(*) n FROM audit_log WHERE action='settings_changed'").fetchone()["n"] == 1


def test_starters_confirm_and_supersede_and_the_builder_refuses_unconfirmed_or_sourceless(env):
    c = env["c"]
    cl = login(env, ADMIN)
    post(cl, "/staff/starters/confirm", csrf=csrf(cl), team_id=env["t1"], game_date="2026-10-20", pitcher_name="Brady Singer", pitcher_id="663903")
    post(cl, "/staff/starters/confirm", csrf=csrf(cl), team_id=env["t1"], game_date="2026-10-20", pitcher_name="Someone Else", pitcher_id="1")
    rows = c.execute("SELECT status, pitcher_name FROM starters ORDER BY id").fetchall()
    assert [r["status"] for r in rows] == ["superseded", "confirmed"]
    sid = c.execute("SELECT id FROM starters WHERE status='confirmed'").fetchone()["id"]
    sug = c.execute("INSERT INTO starters(team_id, game_date, pitcher_id, pitcher_name, status, source) VALUES (?,?,?,?,?,?)", (env["t1"], "2026-10-21", 5, "Sugg", "suggested", "schedule")).lastrowid
    with pytest.raises(identity.EngineError) as e:
        runner.build_starter(env["app"].state.ctx.db_path, env["tmp"] / "d", sug)
    assert "confirmed" in e.value.message
    c.execute("UPDATE teams SET adapter='none' WHERE id=?", (env["t1"],))
    with pytest.raises(identity.EngineError) as e:
        runner.build_starter(env["app"].state.ctx.db_path, env["tmp"] / "d", sid)
    assert "no pitch source" in e.value.message.lower()
    assert post(cl, "/staff/starters/confirm", csrf=csrf(cl), team_id=env["t1"], game_date="2026-10-22", pitcher_name=" ", pitcher_id="1").status_code == 400


def test_a_build_registers_packs_only_when_every_gate_passes(env, tmp_path):
    c = env["c"]
    c.execute("INSERT INTO starters(team_id, game_date, pitcher_id, pitcher_name, status, source) VALUES (?,?,?,?,?,?)", (env["t1"], "2026-10-21", 5, "Sing", "confirmed", "staff"))
    sid = c.execute("SELECT id FROM starters").fetchone()["id"]
    before = c.execute("SELECT COUNT(*) n FROM packs").fetchone()["n"]
    failed = lambda *a, **k: dict(ok=False, built=True, gates=[dict(gate="no_repeats", status="FAIL", side="R", detail="x")])
    r = runner.build_starter(env["app"].state.ctx.db_path, env["tmp"] / "d", sid, failed)
    assert not r["ok"] and r["hashes"] == [] and c.execute("SELECT COUNT(*) n FROM packs").fetchone()["n"] == before
    assert c.execute("SELECT COUNT(*) n FROM audit_log WHERE action='starter_build_failed'").fetchone()["n"] == 1


def test_scheduler_runs_each_job_once_per_interval_records_failures_and_only_suggests_starters(env, tmp_path):
    c = env["c"]
    calls = []

    def resolver(team, on, sport_id=1):
        calls.append((team, sport_id))
        return dict(status="confirmed", team_id=team, game_pk=1, date="2026-10-30", pitcher_id=7, pitcher_name="Probable P", season=2026, checked_at="x")
    dbp = env["app"].state.ctx.db_path
    ran = runner.tick(dbp, tmp_path / "bk", now="2026-10-10T05:00:00.000000Z", resolver=resolver)
    assert set(ran) == {"starters", "reconcile", "backup", "offsite"}
    assert runner.tick(dbp, tmp_path / "bk", now="2026-10-10T05:10:00.000000Z", resolver=resolver) == []
    assert (14, 516) not in calls and {(516, 14), (2310, 11)} <= set(calls)
    st = c.execute("SELECT status, source FROM starters").fetchall()
    assert {(r["status"], r["source"]) for r in st} == {("suggested", "schedule")}                   # suggested, never confirmed by the machine
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("schedule down"))
    runner.tick(dbp, tmp_path / "bk", now="2026-10-10T09:00:00.000000Z", resolver=boom)
    last = c.execute("SELECT ok FROM job_runs WHERE name='starters' ORDER BY id DESC LIMIT 1").fetchone()
    assert last["ok"] == 1                                                                           # a down schedule service is reported per team, not a crash
    assert list((tmp_path / "bk").glob("engine-*.db"))


def test_leaderboard_and_hitter_page_show_counts_and_keep_cameras_apart_and_export_neutralizes_formulas(env):
    c = env["c"]
    for who in ("p1", "p2"):
        tok = identity.create_claim(c, SECRET, env[who])
        conf = TestClient(env["app"]).post("/api/claim/confirm", json={"token": tok}).json()
        cred = conf["credential"]
        batch = [ans(f"{who}-lb-{i:03d}", env["pack"], f"starterL{i % 4}", "zone", "Strike" if i % 2 else "Ball") for i in range(40)]
        r = TestClient(env["app"]).post("/api/answers", json={"answers": batch}, headers={"Authorization": f"Bearer {cred}"})
        assert len(r.json()["stored"]) == 40
    c.execute("UPDATE players SET name='=HYPERLINK(\"x\")' WHERE id=?", (env["p2"],))
    cl = login(env, ADMIN)
    page = cl.get("/staff/leaderboard?mode=train").text
    assert "Strike or ball" in page and "broadcast" in page and "Jordan Smith" in page and "n</th>" in page
    hit = cl.get(f"/staff/player/{env['p1']}").text
    assert "Training, broadcast" in hit and "n=40" in hit and "mid-mid" in hit
    export = cl.get("/staff/export.csv").text
    assert "'=HYPERLINK" in export and "\n=HYPERLINK" not in export and export.count("\n") == 81
    assert cl.get("/staff/leaderboard").text.count("No answers") == 1                                 # assessment board is empty: nothing was answered in assessment mode


def test_admin_can_add_a_team_and_a_coach_whose_token_is_shown_once_and_works(env):
    cl = login(env, ADMIN)
    post(cl, "/staff/admin/team", csrf=csrf(cl), name="Hillsboro Hops", level="High-A", mlb_team_id="419", sport_id="13", adapter="none")
    assert env["c"].execute("SELECT COUNT(*) n FROM teams WHERE name='Hillsboro Hops'").fetchone()["n"] == 1
    dup = post(cl, "/staff/admin/team", csrf=csrf(cl), name="Hillsboro Hops", level="High-A", adapter="none")
    assert dup.status_code == 409
    tid = env["c"].execute("SELECT id FROM teams WHERE name='Hillsboro Hops'").fetchone()["id"]
    r = post(cl, "/staff/admin/coach", csrf=csrf(cl), name="New Coach", team=str(tid))
    token = re.search(r'<p class="mut">([A-Za-z0-9_-]{30,})</p>', r.text).group(1)
    newc = login(env, token)
    assert "Visalia" not in newc.get("/staff/roster").text and newc.get("/staff/admin").status_code == 403
    assert token not in cl.get("/staff/admin").text and token not in newc.get("/staff").text


def test_staff_pages_escape_hostile_names(env):
    env["c"].execute("UPDATE players SET name=? WHERE id=?", ('<script>alert(1)</script>', env["p1"]))
    cl = login(env, ADMIN)
    for path in ("/staff/roster", f"/staff/player/{env['p1']}"):
        t = cl.get(path).text
        assert "<script>alert(1)</script>" not in t and "&lt;script&gt;" in t


def test_deleting_a_hitters_data_is_admin_only_needs_his_name_and_touches_nobody_else(env):
    c = env["c"]
    for pid in (env["p1"], env["p2"]):
        tok = identity.claim_confirm(c, SECRET, identity.create_claim(c, SECRET, pid), "phone")["credential"]
        cred, player = identity.authenticate(c, SECRET, tok)
        from gameplan.engine import answers as A
        A.ingest(c, player, cred, [ans(f"del{pid}-{i:03d}", env["pack"], f"starterL{i % 4}") for i in range(5)])
    coach = login(env, env["coach"])
    r = post(coach, f"/staff/player/{env['p1']}/delete", csrf=csrf(coach), confirm="Jordan Smith")
    assert r.status_code == 403
    admin = login(env, ADMIN)
    wrong = post(admin, f"/staff/player/{env['p1']}/delete", csrf=csrf(admin), confirm="jordan smith")
    assert wrong.status_code == 400 and c.execute("SELECT COUNT(*) n FROM answers WHERE player_id=?", (env["p1"],)).fetchone()["n"] == 5
    ok = post(admin, f"/staff/player/{env['p1']}/delete", csrf=csrf(admin), confirm="Jordan Smith")
    assert ok.status_code == 303
    for t in ("answers", "credentials", "assignments", "codes", "claim_tokens", "heartbeats", "consents", "playlists"):
        assert c.execute(f"SELECT COUNT(*) n FROM {t} WHERE player_id=?", (env["p1"],)).fetchone()["n"] == 0, t
    row = c.execute("SELECT name, org_id, active FROM players WHERE id=?", (env["p1"],)).fetchone()
    assert row["name"].startswith("Deleted hitter") and row["org_id"] is None and row["active"] == 0
    assert c.execute("SELECT COUNT(*) n FROM answers WHERE player_id=?", (env["p2"],)).fetchone()["n"] == 5
    log = c.execute("SELECT detail_json FROM audit_log WHERE action='player.data_deleted'").fetchone()["detail_json"]
    assert "Jordan" not in log and '"answers": 5' in log
