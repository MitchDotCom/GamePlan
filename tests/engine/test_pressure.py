"""Pressure tests on the invariants that matter most: the right person, no lost answers, no duplicates, no way to write under someone else's name.
Random but seeded, so a failure reproduces. Each runs many sequences; the counts are in the test names' docstrings."""
import random

import pytest

from gameplan.engine import answers, db, identity, playlist
from gameplan.engine.identity import EngineError

from .conftest import SECRET
from .test_answers_playlist import ans, make_pack


def active(conn, pid):
    return conn.execute("SELECT COUNT(*) n FROM credentials WHERE player_id=? AND revoked_at IS NULL", (pid,)).fetchone()["n"]


@pytest.mark.parametrize("seed", range(40))
def test_identity_invariants_hold_over_random_sequences(conn, org, seed):
    """40 seeds x 80 random operations over three players: claim, confirm, pair, recover, sign out, staff revoke, guess. After every step:
    a live token authenticates as exactly the player it was issued to, a retired token never authenticates, nobody has more than two live credentials, and a guessed token never works."""
    rng = random.Random(seed)
    players = [org["p1"], org["p2"], org["p3"]]
    issued: dict = {}                    # credential token -> player id
    codes: list = []                     # (pairing code, player id)
    for step in range(80):
        pid = rng.choice(players)
        op = rng.choice(["claim", "claim", "pair", "recover", "signout", "revoke", "guess", "newcode"])
        try:
            if op == "claim":
                tok = identity.create_claim(conn, SECRET, pid)
                got = identity.claim_confirm(conn, SECRET, tok, "dev")
                issued[got["credential"]] = pid
                codes.append((got["pairing_code"], pid))
            elif op == "pair" and codes:
                code, owner = rng.choice(codes)
                got = identity.pair(conn, SECRET, code, "app")
                issued[got["credential"]] = owner
            elif op == "recover":
                rec = identity.create_recovery(conn, SECRET, pid, None)
                got = identity.recover(conn, SECRET, rec["code"], "new")
                issued[got["credential"]] = pid
            elif op == "signout" and issued:
                tok = rng.choice(list(issued))
                auth = identity.authenticate(conn, SECRET, tok)
                if auth:
                    identity.sign_out(conn, auth[0]["id"])
            elif op == "revoke" and issued:
                tok = rng.choice(list(issued))
                auth = identity.authenticate(conn, SECRET, tok)
                if auth:
                    identity.revoke_credential(conn, auth[0]["id"], org["admin"][0])
            elif op == "guess":
                assert identity.authenticate(conn, SECRET, f"guess-{rng.random()}") is None
            elif op == "newcode" and issued:
                tok = rng.choice(list(issued))
                auth = identity.authenticate(conn, SECRET, tok)
                if auth:
                    codes.append((identity.new_pairing_code(conn, SECRET, auth[1]["id"], auth[0]["id"])["pairing_code"], auth[1]["id"]))
        except EngineError:
            pass                                                     # refusals (device limit, used code) are allowed; they must leave the invariants intact
        for tok, owner in issued.items():
            auth = identity.authenticate(conn, SECRET, tok)
            row = conn.execute("SELECT revoked_at FROM credentials WHERE token_hash=?", (__import__("gameplan.engine.security", fromlist=["x"]).keyed_hash(SECRET, tok),)).fetchone()
            if row["revoked_at"]:
                assert auth is None, "a retired credential authenticated"
            else:
                assert auth is not None and auth[1]["id"] == owner, "a live credential authenticated as the wrong player"
        for p in players:
            assert active(conn, p) <= identity.MAX_CREDENTIALS, f"more than {identity.MAX_CREDENTIALS} live credentials"


@pytest.mark.parametrize("seed", range(30))
def test_ingest_is_set_semantics_under_duplication_reordering_and_lost_replies(conn, org, tmp_path, seed):
    """30 seeds x 240 answers: delivered in random chunks, shuffled, with random whole-batch resends (a lost reply) and a share of garbage mixed in.
    The stored rows must equal the set of distinct valid ids, once each, under the right player."""
    rng = random.Random(seed)
    h = make_pack(conn, tmp_path / f"w{seed}", team=org["t1"], n=4)
    tok = identity.create_claim(conn, SECRET, org["p1"])
    cred, player = identity.authenticate(conn, SECRET, identity.claim_confirm(conn, SECRET, tok, "x")["credential"])
    valid = [ans(f"fz{seed:02d}-{i:04d}", h, f"starterL{i % 4}", ["zone", "pitch"][i % 2], ["Strike", "Ball"][i % 3 % 2] if i % 2 == 0 else ["FF", "SL", "CH"][i % 3]) for i in range(240)]
    garbage = [dict(id=f"bad{seed:02d}-{i:04d}", pack="0" * 64, clip="x", task="zone", mode="train", call="Strike") for i in range(40)] + [{"junk": i} for i in range(10)]
    stream = valid + garbage
    rng.shuffle(stream)
    sent = []
    while stream or rng.random() < 0.3:
        k = rng.randint(1, 60)
        chunk, stream = stream[:k], stream[k:]
        sent.append(chunk)
        answers.ingest(conn, player, cred, chunk)
        if rng.random() < 0.4 and sent:                              # the reply was lost: the phone sends an earlier batch again, maybe reordered
            again = list(rng.choice(sent))
            rng.shuffle(again)
            answers.ingest(conn, player, cred, again)
        if not stream:
            break
    rows = conn.execute("SELECT id, player_id FROM answers").fetchall()
    assert sorted(r["id"] for r in rows) == sorted(a["id"] for a in valid)
    assert len({r["id"] for r in rows}) == len(rows) and {r["player_id"] for r in rows} == {org["p1"]}


def test_two_hitters_cannot_write_under_each_others_name_by_any_route(conn, org, tmp_path):
    h = make_pack(conn, tmp_path, team=org["t1"])
    cs = []
    for who in ("p1", "p2"):
        tok = identity.create_claim(conn, SECRET, org[who])
        cs.append(identity.authenticate(conn, SECRET, identity.claim_confirm(conn, SECRET, tok, "x")["credential"]))
    (c1, a), (c2, b) = cs
    answers.ingest(conn, a, c1, [ans("shared-id-0001", h, "starterL0")])
    r = answers.ingest(conn, b, c2, [ans("shared-id-0001", h, "starterL0")])                       # same id from the other hitter
    assert r["stored"] == [] and r["duplicates"] == [] and r["rejected"][0]["reason"] == "id belongs to another record"
    assert conn.execute("SELECT player_id FROM answers WHERE id='shared-id-0001'").fetchone()["player_id"] == org["p1"]
    for hostile in ("player_id", "credential_id", "pid"):
        r = answers.ingest(conn, b, c2, [dict(ans("own-id-0000001", h, "starterL1"), **{hostile: org["p1"]})])
        assert r["stored"] == ["own-id-0000001"]
        assert conn.execute("SELECT player_id, credential_id FROM answers WHERE id='own-id-0000001'").fetchone()["player_id"] == org["p2"]
        conn.execute("DELETE FROM answers WHERE id='own-id-0000001'")


def test_hostile_text_in_every_field_is_stored_inert_or_refused(conn, org, tmp_path):
    h = make_pack(conn, tmp_path, team=org["t1"])
    tok = identity.create_claim(conn, SECRET, org["p1"])
    cred, player = identity.authenticate(conn, SECRET, identity.claim_confirm(conn, SECRET, tok, "x")["credential"])
    evil = ["'; DROP TABLE answers; --", "<script>alert(1)</script>", "=cmd|' /C calc'!A0", "\x00\x01", "A" * 5000, "../../etc/passwd", "‮", "' OR '1'='1"]
    batch = []
    for i, e in enumerate(evil):
        batch.append(dict(ans(f"hostile-{i:05d}", h, "starterL0"), session=e, camera=e, view=e, options=e, app=e, ts=e))
    r = answers.ingest(conn, player, cred, batch)
    assert len(r["stored"]) + len(r["rejected"]) == len(evil)
    assert conn.execute("SELECT COUNT(*) n FROM answers").fetchone()["n"] == len(r["stored"])
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='answers'").fetchone() is not None
    for row in conn.execute("SELECT session, camera, view, options, app_version FROM answers"):
        assert all(v is None or len(v) <= 200 for v in row)


def test_no_secret_ever_reaches_the_audit_log_heartbeats_or_job_records(conn, org, tmp_path):
    secrets_seen = []
    for who in ("p1", "p2"):
        tok = identity.create_claim(conn, SECRET, org[who])
        got = identity.claim_confirm(conn, SECRET, tok, "x")
        rec = identity.create_recovery(conn, SECRET, org[who], org["admin"][0])
        secrets_seen += [tok, got["credential"], got["pairing_code"], rec["code"]]
        identity.recover(conn, SECRET, rec["code"], "y")
    secrets_seen += [org["admin"][1], org["coach"][1]]
    blob = " ".join(str(tuple(r)) for t in ("audit_log", "heartbeats", "job_runs", "credentials", "claim_tokens", "codes", "staff") for r in conn.execute(f"SELECT * FROM {t}"))
    assert not [s for s in secrets_seen if s in blob]


def test_playlist_is_deterministic_for_the_same_data(conn, org, tmp_path):
    make_pack(conn, tmp_path, team=org["t1"], n=6)
    tok = identity.create_claim(conn, SECRET, org["p1"])
    _, player = identity.authenticate(conn, SECRET, identity.claim_confirm(conn, SECRET, tok, "x")["credential"])
    a = playlist.compose(conn, player, "2026-11-01")
    b = playlist.compose(conn, player, "2026-11-01")
    strip = lambda pl: [(p["id"], [i["id"] for i in p["items"]]) for p in pl["packs"]]
    assert strip(a) == strip(b)
