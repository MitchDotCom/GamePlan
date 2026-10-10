import json

import pytest
from fastapi.testclient import TestClient

from gameplan.engine import app as engine_app
from gameplan.engine import db, identity

from .test_answers_playlist import ans, make_pack

SECRET = "test-secret-not-for-production"
ADMIN = "admin-token-at-least-24-characters-long"


@pytest.fixture
def env(tmp_path):
    app = engine_app.create_app(tmp_path / "data", SECRET, ADMIN, trust_proxy=False)
    c = db.connect(app.state.ctx.db_path)
    t1 = identity.add_team(c, "Visalia Rawhide", "A", 516, 14, "tracking_drawn")
    t2 = identity.add_team(c, "Reno Aces", "AAA", 2310, 11, "tracking_drawn")
    p1 = identity.add_player(c, "Jordan Smith", "L", t1, "ORG-1")
    p2 = identity.add_player(c, "Alex Jones", "R", t1, "ORG-2")
    h = make_pack(c, tmp_path / "work", team=t1)
    # make_pack writes content under tmp_path/work/content; copy to the app's content root
    import shutil
    shutil.copytree(tmp_path / "work" / "content", app.state.ctx.content_root, dirs_exist_ok=True)
    cl = TestClient(app)
    yield dict(app=app, c=c, client=cl, t1=t1, t2=t2, p1=p1, p2=p2, pack=h, secret=SECRET)
    c.close()


def claim_and_sign_in(env, who="p1"):
    tok = identity.create_claim(env["c"], SECRET, env[who])
    r = env["client"].post("/api/claim/confirm", json={"token": tok, "label": "test"})
    assert r.status_code == 200, r.text
    return r.json()["credential"], r.json()


def hdr(cred):
    return {"Authorization": f"Bearer {cred}"}


def test_health_config_and_security_headers(env):
    r = env["client"].get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] and r.headers["referrer-policy"] == "no-referrer" and r.headers["x-frame-options"] == "DENY"
    assert env["client"].get("/config.json").json()["engine"] is True
    assert env["client"].get("/config.json").headers["cache-control"] == "no-store"


def test_full_player_flow_claim_me_playlist_answer_and_content(env, tmp_path):
    tok = identity.create_claim(env["c"], SECRET, env["p1"])
    cl = env["client"]
    prev = cl.post("/api/claim/preview", json={"token": tok})
    assert prev.json()["name"] == "Jordan Smith" and prev.json()["team"] == "Visalia Rawhide"
    conf = cl.post("/api/claim/confirm", json={"token": tok, "label": "iPhone"}).json()
    cred = conf["credential"]
    me = cl.get("/api/me", headers=hdr(cred)).json()
    assert me["player"]["name"] == "Jordan Smith" and me["settings"]["pause_ms"] == 150
    pl = cl.get("/api/playlist", headers=hdr(cred)).json()
    assert [p["id"] for p in pl["packs"]] == [env["pack"]]
    item = pl["packs"][0]["items"][0]["id"]
    r = cl.post("/api/answers", headers=hdr(cred), json={"answers": [ans("api-test-0001", env["pack"], item)]}).json()
    assert r["stored"] == ["api-test-0001"] and not r["rejected"]
    assert cl.post("/api/answers", headers=hdr(cred), json={"answers": [ans("api-test-0001", env["pack"], item)]}).json()["duplicates"] == ["api-test-0001"]
    hb = cl.post("/api/heartbeat", headers=hdr(cred), json={"stored": 1, "sent": 1, "unsent": 0, "app": "engine-1", "persisted": True})
    assert hb.status_code == 200 and env["c"].execute("SELECT COUNT(*) n FROM heartbeats").fetchone()["n"] == 1


def test_everything_that_needs_a_credential_refuses_without_one(env):
    cl = env["client"]
    for method, path, body in (("get", "/api/me", None), ("get", "/api/playlist", None), ("post", "/api/answers", {"answers": []}), ("post", "/api/heartbeat", {}),
                               ("post", "/api/signout", {}), ("post", "/api/pairing-code", {}), ("get", f"/content/{env['pack']}/x.mp4", None)):
        for h in (None, {"Authorization": "Bearer nope"}, {"Authorization": "Bearer " + "x" * 300}, {"Authorization": "Basic abc"}):
            r = getattr(cl, method)(path, headers=h, **({"json": body} if body is not None else {}))
            assert r.status_code == 401 and r.json()["code"] == "signed_out", (path, h, r.status_code)


def test_signed_out_and_revoked_credentials_stop_working_at_once(env):
    cred, _ = claim_and_sign_in(env)
    assert env["client"].get("/api/me", headers=hdr(cred)).status_code == 200
    assert env["client"].post("/api/signout", headers=hdr(cred)).status_code == 200
    assert env["client"].get("/api/me", headers=hdr(cred)).status_code == 401
    cred2, _ = claim_and_sign_in(env, "p2")
    cid = env["c"].execute("SELECT id FROM credentials WHERE player_id=?", (env["p2"],)).fetchone()["id"]
    identity.revoke_credential(env["c"], cid, None)
    assert env["client"].get("/api/me", headers=hdr(cred2)).status_code == 401


def test_pairing_for_the_installed_app_over_http(env):
    cred, conf = claim_and_sign_in(env)
    r = env["client"].post("/api/pair", json={"code": conf["pairing_code"], "label": "Home Screen app"})
    assert r.status_code == 200
    new = r.json()["credential"]
    assert env["client"].get("/api/me", headers=hdr(new)).json()["player"]["name"] == "Jordan Smith"
    assert env["client"].get("/api/me", headers=hdr(cred)).status_code == 401            # the browser credential was retired
    assert env["client"].post("/api/pair", json={"code": conf["pairing_code"]}).status_code == 404


def test_a_signed_in_phone_can_ask_for_a_fresh_pairing_code(env):
    cred, _ = claim_and_sign_in(env)
    code = env["client"].post("/api/pairing-code", headers=hdr(cred)).json()["pairing_code"]
    assert len(code) == 8 and env["client"].post("/api/pair", json={"code": code}).status_code == 200


def test_recovery_over_http(env):
    cred, _ = claim_and_sign_in(env)
    rec = identity.create_recovery(env["c"], SECRET, env["p1"], None)
    r = env["client"].post("/api/recover", json={"code": rec["code"], "label": "new phone"})
    assert r.status_code == 200 and env["client"].get("/api/me", headers=hdr(cred)).status_code == 401
    assert env["client"].get("/api/me", headers=hdr(r.json()["credential"])).status_code == 200


def test_guessing_codes_is_throttled(env):
    cl = env["client"]
    codes = [cl.post("/api/pair", json={"code": f"{i:08d}"}).status_code for i in range(30)]
    assert codes[:20] == [404] * 20 and set(codes[20:]) == {429}


def test_bad_bodies_are_refused_cleanly(env):
    cl = env["client"]
    cred, _ = claim_and_sign_in(env)
    h = {**hdr(cred), "Content-Type": "application/json"}
    assert cl.post("/api/answers", headers=hdr(cred), content="x" * 1_100_000).status_code == 413
    for body in ("{not json", "[1,2]", "null", '"str"', ""):
        r = cl.post("/api/answers", headers=h, content=body)
        assert r.status_code == 400 and r.json()["code"] == "bad_json", (body, r.status_code, r.text)
    assert cl.post("/api/answers", headers=hdr(cred), json={"answers": [{}] * 501}).status_code == 413
    assert cl.post("/api/answers", headers=hdr(cred), json={"answers": "nope"}).status_code == 400
    for path in ("/api/claim/preview", "/api/claim/confirm", "/api/pair", "/api/recover"):
        assert cl.post(path, headers={"Content-Type": "application/json"}, content="{bad").status_code == 400


def test_content_is_served_only_with_a_credential_and_only_inside_its_folder(env):
    cred, _ = claim_and_sign_in(env)
    for bad in (f"/content/{env['pack']}/../../engine.db", "/content/..%2f..%2fengine.db/x", f"/content/{env['pack']}/%2e%2e%2fengine.db", "/content/zz/x.mp4", f"/content/{env['pack']}/nope.mp4"):
        assert env["client"].get(bad, headers=hdr(cred)).status_code in (400, 404, 422), bad


def test_claim_page_is_served_without_leaking_the_token_to_other_sites(env):
    r = env["client"].get("/c/some-token-value")
    assert r.status_code == 200 and r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-store"


def test_assessment_keys_are_not_in_any_player_response(env, tmp_path):
    c = env["c"]
    a = make_pack(c, tmp_path / "work", kind="assess", mode="assess", team=env["t1"], pk_id="asx")
    import shutil
    shutil.copytree(tmp_path / "work" / "content", env["app"].state.ctx.content_root, dirs_exist_ok=True)
    cred, _ = claim_and_sign_in(env)
    pl = env["client"].get("/api/playlist", headers=hdr(cred)).json()
    m = [p for p in pl["packs"] if p["id"] == a][0]
    assert all(i["keys"] is None for i in m["items"])
    assert "strike" not in json.dumps(m)


def test_server_secret_is_required():
    with pytest.raises(RuntimeError):
        engine_app.create_app("/tmp/x-unused", "short")


def test_heartbeat_asks_the_phone_to_resend_when_the_server_holds_fewer_answers_than_the_phone_sent(env):
    from gameplan.engine import answers as A
    from .test_answers_playlist import ans
    cl = env["client"]
    cred, _ = claim_and_sign_in(env)
    batch = [ans(f"resend{i:03d}", env["pack"], f"starterL{i % 4}") for i in range(6)]
    assert len(cl.post("/api/answers", headers=hdr(cred), json={"answers": batch}).json()["stored"]) == 6
    ok = cl.post("/api/heartbeat", headers=hdr(cred), json={"stored": 6, "sent": 6, "unsent": 0}).json()
    assert ok["resend"] is False
    env["c"].execute("DELETE FROM answers WHERE id IN ('resend004','resend005')")          # what a restore from an older backup looks like
    lost = cl.post("/api/heartbeat", headers=hdr(cred), json={"stored": 6, "sent": 6, "unsent": 0}).json()
    assert lost["resend"] is True and env["c"].execute("SELECT COUNT(*) n FROM audit_log WHERE action='resend_requested'").fetchone()["n"] == 1
    again = cl.post("/api/answers", headers=hdr(cred), json={"answers": batch}).json()      # the phone resends everything
    assert sorted(again["stored"]) == ["resend004", "resend005"] and len(again["duplicates"]) == 4
    assert cl.post("/api/heartbeat", headers=hdr(cred), json={"stored": 6, "sent": 6, "unsent": 0}).json()["resend"] is False
