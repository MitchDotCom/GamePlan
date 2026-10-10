import json
import re

import pytest
from fastapi.testclient import TestClient

from gameplan.engine import app as engine_app
from gameplan.engine import db, identity

from .conftest import SECRET

ADMIN = "admin-token-for-tests-123456"


def consent_file(tmp_path, version="v1", required=True):
    p = tmp_path / "consent.json"
    p.write_text(json.dumps(dict(version=version, required=required, title="About your data", paragraphs=["We record your answers.", "Coaches see them."], button="I agree")))
    return p


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_CONSENT_FILE", str(consent_file(tmp_path)))
    app = engine_app.create_app(tmp_path / "data", SECRET, ADMIN, trust_proxy=False)
    c = db.connect(tmp_path / "data" / "engine.db")
    t = identity.add_team(c, "Visalia", "A", 516, 14, "none")
    p = identity.add_player(c, "Test Hitter", "R", t, "T-1")
    tok = identity.create_claim(c, SECRET, p)
    cred = TestClient(app).post("/api/claim/confirm", json={"token": tok}).json()["credential"]
    return dict(app=app, cl=TestClient(app), cred=cred, c=c, pid=p, tmp=tmp_path)


def H(cred):
    return {"Authorization": f"Bearer {cred}"}


def test_nothing_is_served_or_stored_until_he_agrees(env):
    cl, h = env["cl"], H(env["cred"])
    me = cl.get("/api/me", headers=h).json()
    assert me["consent"]["accepted"] is False and me["consent"]["paragraphs"][0].startswith("We record")
    for r in (cl.get("/api/playlist", headers=h), cl.post("/api/answers", headers=h, json={"answers": []})):
        assert r.status_code == 403 and r.json()["code"] == "consent_required"
    assert cl.post("/api/consent", headers=h, json={"version": "v1"}).json()["ok"]
    assert cl.get("/api/me", headers=h).json()["consent"]["accepted"] is True
    assert cl.get("/api/playlist", headers=h).status_code == 200
    rows = env["c"].execute("SELECT version, credential_id FROM consents WHERE player_id=?", (env["pid"],)).fetchall()
    assert len(rows) == 1 and rows[0]["version"] == "v1"
    assert env["c"].execute("SELECT COUNT(*) n FROM audit_log WHERE action='consent.accept'").fetchone()["n"] == 1


def test_agreeing_twice_stores_one_row_and_a_wrong_version_is_refused(env):
    cl, h = env["cl"], H(env["cred"])
    assert cl.post("/api/consent", headers=h, json={"version": "old"}).status_code == 409
    cl.post("/api/consent", headers=h, json={"version": "v1"})
    cl.post("/api/consent", headers=h, json={"version": "v1"})
    assert env["c"].execute("SELECT COUNT(*) n FROM consents").fetchone()["n"] == 1


def test_a_new_version_asks_everyone_again(env, monkeypatch):
    cl, h = env["cl"], H(env["cred"])
    cl.post("/api/consent", headers=h, json={"version": "v1"})
    monkeypatch.setenv("ENGINE_CONSENT_FILE", str(consent_file(env["tmp"], "v2")))
    app2 = engine_app.create_app(env["tmp"] / "data", SECRET, ADMIN, trust_proxy=False)
    cl2 = TestClient(app2)
    assert cl2.get("/api/me", headers=h).json()["consent"]["accepted"] is False
    assert cl2.get("/api/playlist", headers=h).status_code == 403


def test_one_hitters_agreement_does_not_cover_another(env):
    c = env["c"]
    p2 = identity.add_player(c, "Second Hitter", "L", 1, "T-2")
    cred2 = env["cl"].post("/api/claim/confirm", json={"token": identity.create_claim(c, SECRET, p2)}).json()["credential"]
    env["cl"].post("/api/consent", headers=H(env["cred"]), json={"version": "v1"})
    assert env["cl"].get("/api/playlist", headers=H(cred2)).status_code == 403


def test_consent_can_be_switched_off_by_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_CONSENT_FILE", str(consent_file(tmp_path, required=False)))
    app = engine_app.create_app(tmp_path / "data", SECRET, ADMIN, trust_proxy=False)
    assert app.state.get_conn is not None
