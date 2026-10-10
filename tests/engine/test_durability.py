"""Durability, load and restore drill. Every answer the service acknowledged must survive a hard kill, and the database must stay intact."""
import os
import pathlib
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from gameplan.engine import answers, backup, db, identity

from .conftest import SECRET
from .test_answers_playlist import ans, make_pack

SRC = str(pathlib.Path(__file__).resolve().parents[2] / "src")

CHILD = textwrap.dedent("""
    import sys
    sys.path.insert(0, {src!r})
    from gameplan.engine import answers, db, identity
    c = db.connect(sys.argv[1])
    cred, player = identity.authenticate(c, {secret!r}, sys.argv[2])
    pack, n = sys.argv[3], 0
    while True:
        batch = [dict(id="dur%07d-%d" % (n, i), pack=pack, clip="starterL%d" % (i % 4), task="zone", call="Strike", mode="train", rt_ms=400, pause_ms=100,
                      camera="broadcast", ts=db.now(), q_order=1, clip_trial=1, session="s") for i in range(5)]
        out = answers.ingest(c, player, cred, batch)
        print(",".join(out["stored"]), flush=True)
        n += 1
""")


def test_kill_minus_nine_loses_no_acknowledged_answer(conn, org, tmp_path):
    h = make_pack(conn, tmp_path, team=org["t1"])
    tok = identity.claim_confirm(conn, SECRET, identity.create_claim(conn, SECRET, org["p1"]), "phone")["credential"]
    path = conn.execute("PRAGMA database_list").fetchone()["file"]
    acked = set()
    for round_ in range(3):
        p = subprocess.Popen([sys.executable, "-c", CHILD.format(src=SRC, secret=SECRET), path, tok, h], stdout=subprocess.PIPE, text=True)
        t0 = time.time()
        while time.time() - t0 < 1.0:
            line = p.stdout.readline()
            if line.strip():
                acked.update(line.strip().split(","))
        p.send_signal(signal.SIGKILL)
        p.wait()
        for line in p.stdout.read().splitlines():            # lines the child printed before dying are acknowledged too
            if line.strip():
                acked.update(line.strip().split(","))
        # reopen exactly as a restarted service would
        c2 = db.connect(path)
        assert c2.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        have = {r["id"] for r in c2.execute("SELECT id FROM answers")}
        missing = acked - have
        assert not missing, f"{len(missing)} acknowledged answers lost after kill -9 (round {round_})"
        c2.close()
    assert len(acked) > 50, "child wrote too little to prove anything"
    assert len(have) >= len(acked)


def test_load_80_then_800_hitters_zero_lost_rows_and_coach_reads_stay_fast(conn, org, tmp_path):
    h = make_pack(conn, tmp_path, team=org["t1"], n=8)
    for count in (80, 800):
        ids = []
        for i in range(count):
            pid = identity.add_player(conn, f"Hitter {count}-{i}", "R", org["t1"], f"L{count}-{i}")
            ids.append(pid)
        t0 = time.time()
        total = 0
        lat = []
        for pid in ids:
            tok = identity.claim_confirm(conn, SECRET, identity.create_claim(conn, SECRET, pid), "p")["credential"]
            cred, player = identity.authenticate(conn, SECRET, tok)
            batch = [ans(f"ld{count}-{pid}-{j}", h, f"starterL{j % 8}") for j in range(20)]
            s = time.time()
            out = answers.ingest(conn, player, cred, batch)
            lat.append(time.time() - s)
            assert len(out["stored"]) == 20 and not out["rejected"]
            total += 20
        lat.sort()
        p95 = lat[int(len(lat) * 0.95) - 1]
        n_db = conn.execute("SELECT COUNT(*) n FROM answers WHERE id LIKE ?", (f"ld{count}-%",)).fetchone()["n"]
        assert n_db == total, "rows lost under load"
        assert p95 < 0.5, f"p95 ingest {p95:.3f}s at {count} hitters"
        s = time.time()
        conn.execute("SELECT player_id, COUNT(*), SUM(correct) FROM answers GROUP BY player_id").fetchall()
        assert time.time() - s < 2.0


def test_restore_drill_backup_opens_and_matches_then_serves_after_restore(conn, org, tmp_path):
    h = make_pack(conn, tmp_path, team=org["t1"])
    tok = identity.claim_confirm(conn, SECRET, identity.create_claim(conn, SECRET, org["p1"]), "phone")["credential"]
    cred, player = identity.authenticate(conn, SECRET, tok)
    answers.ingest(conn, player, cred, [ans(f"restore-{i}", h, f"starterL{i % 4}") for i in range(30)])
    live = conn.execute("PRAGMA database_list").fetchone()["file"]
    b = backup.backup(live, tmp_path / "bk")
    answers.ingest(conn, player, cred, [ans(f"restore-late-{i}", h, f"starterL{i % 4}") for i in range(5)])      # written after the backup
    r = backup.restore_check(b, live)
    assert r["ok"] and r["backup"]["answers"] == 30 and r["live"]["answers"] == 35
    # disaster: live file gone; restore the copy and confirm the old credential still authenticates and answers are intact
    restored = tmp_path / "restored.db"
    restored.write_bytes(pathlib.Path(b).read_bytes())
    c2 = db.connect(restored)
    assert c2.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert c2.execute("SELECT COUNT(*) n FROM answers").fetchone()["n"] == 30
    assert identity.authenticate(c2, SECRET, tok) is not None
    cred2, player2 = identity.authenticate(c2, SECRET, tok)
    again = answers.ingest(c2, player2, cred2, [ans(f"restore-late-{i}", h, f"starterL{i % 4}") for i in range(5)])
    assert len(again["stored"]) == 5, "phone outbox replay after a restore must fill the gap"


def test_restore_command_replaces_the_live_file_keeps_the_old_one_and_refuses_a_bad_backup(conn, org, tmp_path):
    h = make_pack(conn, tmp_path, team=org["t1"])
    tok = identity.claim_confirm(conn, SECRET, identity.create_claim(conn, SECRET, org["p1"]), "phone")["credential"]
    cred, player = identity.authenticate(conn, SECRET, tok)
    answers.ingest(conn, player, cred, [ans(f"cmdrest-{i}", h, f"starterL{i % 4}") for i in range(10)])
    live = pathlib.Path(conn.execute("PRAGMA database_list").fetchone()["file"])
    b = backup.backup(live, tmp_path / "bk")
    answers.ingest(conn, player, cred, [ans(f"cmdrest-late-{i}", h, f"starterL{i % 4}") for i in range(3)])
    conn.close()
    out = backup.restore(b, live)
    assert out["restored"]["answers"] == 10 and pathlib.Path(out["kept_old"]).exists()
    assert backup.counts(live)["answers"] == 10 and backup.counts(out["kept_old"])["answers"] == 13
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database" * 100)
    with pytest.raises(Exception):
        backup.restore(bad, live)
    assert backup.counts(live)["answers"] == 10                    # a refused restore touched nothing
