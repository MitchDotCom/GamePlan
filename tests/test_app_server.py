import json
import threading
import urllib.error
import urllib.request

import pytest

from gameplan import app_content as AC
from gameplan import app_server as AS


def _srv(tmp_path, token=None, keys=None):
    (tmp_path / "content").mkdir(exist_ok=True)
    srv, store = AS.serve(tmp_path / "content", tmp_path / "data", 0, token, keys)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, store, f"http://127.0.0.1:{srv.server_address[1]}"


def _post(url, body, token=None):
    req = urllib.request.Request(url + "/api/trials", json.dumps(body).encode(), {"Content-Type": "application/json", **({"X-Token": token} if token else {})})
    return urllib.request.urlopen(req)


T = dict(player="P", session="s", mode="train", ts="t", pack="pk", clip="c1", clip_trial=1, task="zone", q_order=1, ask="both", pause_ms=100, call="GO", rt_ms=400, key="", correct="", id="a1")


def test_sync_is_idempotent_and_csv_has_rows(tmp_path):
    srv, store, url = _srv(tmp_path)
    assert json.load(_post(url, {"trials": [T, dict(T, id="a2", task="pitch")]}))["stored"] == 2
    assert json.load(_post(url, {"trials": [T]}))["stored"] == 0               # same id again: not stored twice
    csv_text = urllib.request.urlopen(url + "/api/trials.csv").read().decode()
    assert csv_text.count("\n") == 3 and csv_text.startswith("player,session")
    srv.shutdown()


def test_token_required_when_set(tmp_path):
    srv, store, url = _srv(tmp_path, token="s3")
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(url, {"trials": [T]})
    assert e.value.code == 401
    assert json.load(_post(url, {"trials": [T]}, "s3"))["stored"] == 1
    srv.shutdown()


def test_assessment_rows_are_scored_server_side_from_private_keys(tmp_path):
    kf = tmp_path / "k.json"
    kf.write_text(json.dumps({"pk/c1": dict(zone_go=True, pitch_go=False)}))
    srv, store, url = _srv(tmp_path, keys=kf)
    _post(url, {"trials": [T, dict(T, id="a2", task="pitch", call="GO")]})
    rows = {r["task"]: r for r in store.rows()}
    assert (rows["zone"]["key"], rows["zone"]["correct"]) == ("GO", 1)
    assert (rows["pitch"]["key"], rows["pitch"]["correct"]) == ("NO-GO", 0)
    srv.shutdown()


def test_assessment_pack_ships_no_keys_but_private_file_has_them(tmp_path):
    rows = [dict(play_id=f"{i:012d}xxxxxxxxxxxx", plateTime=0.4, pitch_type="FF", px=0.1, pz=2.5, sz_top=3.5, sz_bot=1.5, stand="R", start_speed=93, pfxX=1, pfxZ=1) for i in range(3)]
    fake = lambda p, work, out: (out.parent.mkdir(parents=True, exist_ok=True), out.write_bytes(b"x"), dict(release=1.6))[2]
    train, priv = AC.build_pack("t", "T", "", rows, tmp_path, tmp_path, "train", 3, fake)
    assess, priv2 = AC.build_pack("a", "A", "", rows, tmp_path, tmp_path, "assess", 3, fake)
    assert all(i["keys"] for i in train["items"]) and all(i["keys"] is None for i in assess["items"])
    assert priv2 and all("zone_go" in v for v in priv2.values())
    assert assess["items"][0]["meta"]["ride_in"] == 12.0 and assess["items"][0]["meta"]["run_in"] == 12.0     # R batter: feed pfxX positive = away
