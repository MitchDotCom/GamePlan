import re

import pytest
from fastapi.testclient import TestClient

from gameplan.engine import app as engine_app
from gameplan.engine import db, identity

from .test_answers_playlist import make_pack
from .test_staff import ADMIN, SECRET, login, post

import shutil


@pytest.fixture
def env(tmp_path):
    app = engine_app.create_app(tmp_path / "data", SECRET, ADMIN, trust_proxy=False)
    c = db.connect(app.state.ctx.db_path)
    t1 = identity.add_team(c, "Visalia Rawhide", "Single-A", 516, 14, "tracking_drawn")
    p1 = identity.add_player(c, "Jordan Smith", "L", t1, "ORG-1")
    make_pack(c, tmp_path / "work", team=t1)
    shutil.copytree(tmp_path / "work" / "content", app.state.ctx.content_root, dirs_exist_ok=True)
    tok = identity.create_claim(c, SECRET, p1)
    cred = TestClient(app).post("/api/claim/confirm", json={"token": tok}).json()["credential"]
    yield dict(app=app, c=c, cred=cred, p1=p1, tmp=tmp_path)
    c.close()


def test_a_hitters_credential_opens_nothing_on_the_staff_side(env):
    cl = TestClient(env["app"], follow_redirects=False)
    h = {"Authorization": f"Bearer {env['cred']}"}
    for path in ("/staff", "/staff/roster", "/staff/leaderboard", "/staff/export.csv", "/staff/packs", "/staff/audit", f"/staff/player/{env['p1']}"):
        assert cl.get(path, headers=h).status_code in (303, 401, 403), path
        cl.cookies.set("staff", env["cred"])
        assert cl.get(path).status_code in (303, 401, 403), path
        cl.cookies.clear()
    assert cl.post("/staff/player/1/claim", headers=h, content="csrf=x", ).status_code in (303, 401, 403)


def test_a_staff_token_opens_nothing_on_the_hitter_side(env):
    cl = TestClient(env["app"])
    for path in ("/api/me", "/api/playlist"):
        assert cl.get(path, headers={"Authorization": f"Bearer {ADMIN}"}).status_code == 401
    assert cl.post("/api/answers", headers={"Authorization": f"Bearer {ADMIN}"}, json={"answers": []}).status_code == 401


def test_internal_files_and_framework_pages_are_not_reachable(env):
    cl = TestClient(env["app"])
    for path in ("/docs", "/redoc", "/openapi.json", "/engine.db", "/engine_data/engine.db", "/data/engine.db", "/../engine.db", "/%2e%2e/engine.db", "/..%2fengine.db", "/content/../engine.db",
                 "/src/gameplan/engine/app.py", "/pyproject.toml", "/CLAUDE.md", "/.git/config", "/.env"):
        r = cl.get(path)
        assert r.status_code in (401, 404, 405) or "SECRET" not in r.text and "sqlite" not in r.text.lower()[:200], (path, r.status_code)
        assert not r.content.startswith(b"SQLite format")


def test_unusual_methods_and_paths_are_refused_without_a_server_error(env):
    cl = TestClient(env["app"], raise_server_exceptions=False)
    for method in ("put", "delete", "patch"):
        for path in ("/api/answers", "/api/me", "/api/claim/confirm", "/staff/roster"):
            assert getattr(cl, method)(path).status_code in (401, 403, 404, 405, 411), (method, path)
    for path in ("/api/" + "x" * 3000, "/c/" + "a" * 5000, "/content/" + "a" * 64 + "/" + "b" * 500, "/api/%00", "/c/%00", "/staff/player/abc", "/staff/player/99999999999999999999"):
        r = cl.get(path, headers={"Authorization": f"Bearer {env['cred']}"})
        assert r.status_code < 500, (path[:40], r.status_code)


def test_injection_in_tokens_codes_and_headers_never_authenticates_or_errors(env):
    cl = TestClient(env["app"], raise_server_exceptions=False)
    for bad in ("' OR 1=1 --", "\" OR \"\"=\"", "%27%20OR%201%3D1", "x' UNION SELECT token_hash FROM credentials --", "\r\nX-Injected: 1", "null", "None", "0", "{}", "[]"):
        assert cl.post("/api/pair", json={"code": bad}).status_code in (400, 404, 429)
        assert cl.post("/api/claim/preview", json={"token": bad}).status_code in (400, 404, 429)
        try:
            r = cl.get("/api/me", headers={"Authorization": "Bearer " + bad.replace("\r", "").replace("\n", "")})
        except Exception:
            continue
        assert r.status_code == 401
    r = cl.get("/api/me", headers={"Authorization": f"Bearer {env['cred']}", "X-Forwarded-For": "1.2.3.4, ' OR 1=1"})
    assert r.status_code == 200 and "x-injected" not in {k.lower() for k in r.headers}


def test_staff_login_is_throttled_and_a_wrong_token_never_sets_a_cookie(env):
    cl = TestClient(env["app"], follow_redirects=False)
    codes = []
    for i in range(30):
        r = post(cl, "/staff/login", token=f"wrong-token-{i}")
        codes.append(r.status_code)
        assert "set-cookie" not in r.headers
    assert 429 in codes and codes[0] == 401


def test_a_forged_or_replayed_staff_cookie_fails(env):
    cl = TestClient(env["app"], follow_redirects=False)
    for forged in ("", "admin", ADMIN[:-1], ADMIN + "x", "' OR 1=1", "A" * 400):
        cl.cookies.clear()
        cl.cookies.set("staff", forged)
        assert cl.get("/staff/roster").status_code == 303
    good = login(env, ADMIN)
    assert good.get("/staff/roster").status_code == 200
    c = env["c"]
    c.execute("UPDATE staff SET revoked_at=? WHERE role='admin'", (db.now(),))
    assert good.get("/staff/roster").status_code == 303                          # revoking a staff login ends it at once, cookie or not


def test_the_csrf_token_of_one_session_does_not_work_for_another_staff_member(env):
    c = env["c"]
    other_id, other_tok = identity.create_staff(c, SECRET, "Other Admin", "admin")
    a, b = login(env, ADMIN), login(env, other_tok)
    token_a = re.search(r'name="csrf" value="([0-9a-f]{32})"', a.get("/staff/roster").text).group(1)
    r = post(b, f"/staff/player/{env['p1']}/claim", csrf=token_a)
    assert r.status_code == 403


def test_responses_carry_no_secret_material(env):
    cl = TestClient(env["app"])
    for path, h in (("/api/me", {"Authorization": f"Bearer {env['cred']}"}), ("/api/playlist", {"Authorization": f"Bearer {env['cred']}"}), ("/healthz", {}), ("/config.json", {})):
        text = cl.get(path, headers=h).text
        assert SECRET not in text and ADMIN not in text and "token_hash" not in text and "key" not in text.lower().replace("keys", "").replace("monkey", "") or path == "/api/playlist"
