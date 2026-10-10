import sqlite3

import pytest

from gameplan.engine import analytics, answers, backup, db, identity, reconcile

from .conftest import SECRET
from .test_answers_playlist import ans, make_pack, signed  # noqa: F401


def test_reconcile_flags_possible_loss_stale_unsent_silent_and_never_claimed(conn, org, signed, tmp_path):  # noqa: F811
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    answers.ingest(conn, player, cred, [ans("rrrrrrrr-1", h, "starterL0")])
    # p1 says it sent 5 but the server holds 1: possible loss
    conn.execute("INSERT INTO heartbeats(player_id, credential_id, ts, stored, sent, unsent, app_version) VALUES (?,?,?,?,?,?,?)", (org["p1"], cred["id"], db.now(), 5, 5, 0, "engine-1"))
    kinds = {(f["kind"], f["player_id"]) for f in reconcile.findings(conn)}
    assert ("possible_loss", org["p1"]) in kinds
    assert ("never_claimed", org["p2"]) in kinds and ("never_claimed", org["p3"]) in kinds
    conn.execute("DELETE FROM heartbeats")
    conn.execute("INSERT INTO heartbeats(player_id, credential_id, ts, stored, sent, unsent, app_version) VALUES (?,?,?,?,?,?,?)", (org["p1"], cred["id"], "2020-01-01T00:00:00.000000Z", 3, 1, 2, "engine-1"))
    conn.execute("UPDATE answers SET server_ts='2019-01-01T00:00:00.000000Z'")
    conn.execute("UPDATE credentials SET created_at='2019-01-01T00:00:00.000000Z'")
    kinds = {f["kind"] for f in reconcile.findings(conn) if f["player_id"] == org["p1"]}
    assert {"stale_unsent", "silent"} <= kinds and "possible_loss" not in kinds
    assert all(f["player_id"] == org["p1"] or f["kind"] == "never_claimed" for f in reconcile.findings(conn, [org["t1"]]))


def test_a_fresh_claim_link_is_not_flagged_never_claimed_yet(conn, org):
    identity.create_claim(conn, SECRET, org["p2"])
    assert ("never_claimed", org["p2"]) not in {(f["kind"], f["player_id"]) for f in reconcile.findings(conn)}


def test_backup_is_consistent_readable_pruned_and_restore_check_passes(conn, org, signed, tmp_path):  # noqa: F811
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    answers.ingest(conn, player, cred, [ans(f"bbbbbbbb-{i}", h, f"starterL{i}") for i in range(4)])
    live = tmp_path / "engine.db"
    first = backup.backup(live, tmp_path / "bk", keep=2)
    assert backup.counts(first)["answers"] == 4
    answers.ingest(conn, player, cred, [ans("bbbbbbbb-9", h, "starterL0")])
    second = backup.backup(live, tmp_path / "bk", keep=2)
    chk = backup.restore_check(first, live)
    assert chk["ok"] and chk["backup"]["answers"] == 4 and chk["live"]["answers"] == 5
    third = backup.backup(live, tmp_path / "bk", keep=2)
    assert first != second != third and not first.exists() and second.exists() and third.exists()     # back-to-back backups never share a name; the oldest is pruned


def test_a_corrupt_backup_fails_loudly(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database at all" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        backup.counts(bad)


def test_ledger_rows_come_from_live_answers_scoped_by_team_and_keep_same_name_players_apart(conn, org, signed, tmp_path):  # noqa: F811
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    answers.ingest(conn, player, cred, [ans("llllllll-1", h, "starterL1"), ans("llllllll-2", h, "starterL2")])
    answers.void(conn, "llllllll-2", "test", None)
    rs = analytics.rows(conn, [org["t1"]])
    assert [r["id"] for r in rs] == ["llllllll-1"] and rs[0]["player"] == "Jordan Smith" and rs[0]["camera_class"] == "broadcast"
    assert analytics.rows(conn, [org["t2"]]) == [] and analytics.rows(conn, []) == []
    twin = identity.add_player(conn, "Jordan Smith", "R", org["t1"], "ORG-TWIN")
    assert analytics.rows(conn, [org["t1"]])[0]["player"] == f"Jordan Smith (#{org['p1']})" and twin != org["p1"]
