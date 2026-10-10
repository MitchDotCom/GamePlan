import pathlib

import pytest
from fastapi.testclient import TestClient

from gameplan.engine import app as engine_app
from gameplan.engine import backup, db, offsite, runner

from .conftest import SECRET


class FakeS3:
    def __init__(self, corrupt=False):
        self.objects, self.corrupt = {}, corrupt

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.objects[(bucket, key)] = pathlib.Path(path).read_bytes()
        self.extra = ExtraArgs

    def head_object(self, Bucket, Key):
        return dict(ContentLength=len(self.objects[(Bucket, Key)]) - (1 if self.corrupt else 0))


def test_offsite_copies_the_newest_backup_and_verifies_its_size(conn, tmp_path, monkeypatch):
    live = conn.execute("PRAGMA database_list").fetchone()["file"]
    backup.backup(live, tmp_path / "bk")
    newest = backup.backup(live, tmp_path / "bk")
    s3 = FakeS3()
    r = offsite.push(tmp_path / "bk", client=s3, bucket="b")
    assert r["status"] == "ok" and r["key"].endswith(newest.name) and s3.extra == {"ServerSideEncryption": "AES256"}
    assert s3.objects[("b", r["key"])] == pathlib.Path(newest).read_bytes()


def test_a_short_copy_is_a_failure_not_a_success(conn, tmp_path):
    live = conn.execute("PRAGMA database_list").fetchone()["file"]
    backup.backup(live, tmp_path / "bk")
    with pytest.raises(RuntimeError, match="bytes"):
        offsite.push(tmp_path / "bk", client=FakeS3(corrupt=True), bucket="b")


def test_without_a_bucket_it_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("OFFSITE_BUCKET", raising=False)
    assert offsite.push(tmp_path) == dict(status="not_configured") and not offsite.configured()


def test_tick_runs_backup_then_offsite_and_records_a_failed_offsite(conn, tmp_path, monkeypatch):
    live = conn.execute("PRAGMA database_list").fetchone()["file"]
    monkeypatch.setenv("OFFSITE_BUCKET", "b")
    monkeypatch.setattr(offsite, "_client", lambda: FakeS3(corrupt=True))
    ran = runner.tick(pathlib.Path(live), tmp_path / "bk", resolver=lambda *a, **k: dict(status="no_game"))
    assert ran.index("backup") < ran.index("offsite")
    rows = {r["name"]: r["ok"] for r in conn.execute("SELECT name, ok FROM job_runs")}
    assert rows["backup"] == 1 and rows["offsite"] == 0


def test_deep_health_is_503_until_a_backup_exists_then_200(tmp_path, monkeypatch):
    monkeypatch.delenv("OFFSITE_BUCKET", raising=False)
    monkeypatch.setenv("ENGINE_SCHEDULER", "1")
    app = engine_app.create_app(tmp_path / "data", SECRET, None, trust_proxy=False)
    cl = TestClient(app)                                              # no lifespan started, so no scheduler has run
    r = cl.get("/healthz/deep")
    assert r.status_code == 503 and "backup" in r.json()["problems"][0] and r.json()["offsite_configured"] is False
    runner.tick(tmp_path / "data" / "engine.db", tmp_path / "data" / "backups", resolver=lambda *a, **k: dict(status="no_game"))
    assert cl.get("/healthz/deep").status_code == 200


def test_deep_health_flags_a_configured_offsite_that_has_not_worked(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFSITE_BUCKET", "b")
    monkeypatch.setattr(offsite, "_client", lambda: FakeS3(corrupt=True))
    app = engine_app.create_app(tmp_path / "data", SECRET, None, trust_proxy=False)
    runner.tick(tmp_path / "data" / "engine.db", tmp_path / "data" / "backups", resolver=lambda *a, **k: dict(status="no_game"))
    r = TestClient(app).get("/healthz/deep")
    assert r.status_code == 503 and any("offsite" in p for p in r.json()["problems"])
