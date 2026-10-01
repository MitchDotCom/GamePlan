import json
import time
import urllib.request

from gameplan.desktop import start_server
from gameplan.server import Job


def test_launcher_serves_the_app_and_api(tmp_path):
    url, stop = start_server(tmp_path / "league", tmp_path / "app")
    try:
        assert b"GamePlan" in urllib.request.urlopen(url).read()
        games = json.load(urllib.request.urlopen(url + "api/games"))["games"]
        assert all(g["status"] == "ready" for g in games)          # only the demo games shipped with the repo; no data folder yet
        d = json.load(urllib.request.urlopen(url + "api/download"))
        assert d["running"] is False and d["files"] == 0 and d["total"] == 195
    finally:
        stop()


def test_build_job_runs_in_its_own_process():
    j = Job(time.sleep, (0.5,))
    assert j.poll() is None
    for _ in range(100):
        if j.poll() is not None:
            break
        time.sleep(0.1)
    assert j.poll() == 0 and j.returncode == 0
