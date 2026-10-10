from gameplan.engine import db, identity

from .conftest import SECRET


def phone(conn, org, pid=None):
    pid = pid or org["p1"]
    got = identity.claim_confirm(conn, SECRET, identity.create_claim(conn, SECRET, pid), "iPhone")
    return identity.authenticate(conn, SECRET, got["credential"]), got["credential"]


def test_a_guest_code_signs_him_in_on_an_ipad_and_leaves_his_phone_signed_in(conn, org):
    (cred, player), phone_tok = phone(conn, org)
    code = identity.new_guest_code(conn, SECRET, player["id"], cred["id"])["pairing_code"]
    got = identity.pair(conn, SECRET, code, "iPad")
    assert got["shared"] is True and got["player"]["id"] == org["p1"]
    assert identity.authenticate(conn, SECRET, phone_tok) is not None             # the phone is untouched
    ipad_cred, _ = identity.authenticate(conn, SECRET, got["credential"])
    assert ipad_cred["shared"] == 1


def test_a_guest_code_works_once_and_the_ipad_does_not_use_a_phone_slot(conn, org):
    (cred, player), _ = phone(conn, org)
    code = identity.new_guest_code(conn, SECRET, player["id"], cred["id"])["pairing_code"]
    identity.pair(conn, SECRET, code, "iPad")
    try:
        identity.pair(conn, SECRET, code, "iPad")
        assert False, "second use must fail"
    except identity.EngineError as e:
        assert e.status == 404
    second_phone = identity.claim_confirm(conn, SECRET, identity.create_claim(conn, SECRET, org["p1"]), "second phone")       # still room: 1 phone + 1 iPad
    assert second_phone["credential"]


def test_the_ipad_credential_is_for_the_right_hitter_not_the_one_before_him(conn, org):
    (c1, p1), _ = phone(conn, org, org["p1"])
    (c2, p2), _ = phone(conn, org, org["p2"])
    g1 = identity.pair(conn, SECRET, identity.new_guest_code(conn, SECRET, p1["id"], c1["id"])["pairing_code"], "iPad")
    identity.sign_out(conn, identity.authenticate(conn, SECRET, g1["credential"])[0]["id"])
    assert identity.authenticate(conn, SECRET, g1["credential"]) is None
    g2 = identity.pair(conn, SECRET, identity.new_guest_code(conn, SECRET, p2["id"], c2["id"])["pairing_code"], "iPad")
    assert identity.authenticate(conn, SECRET, g2["credential"])[1]["id"] == org["p2"]


def test_only_three_ipad_sign_ins_stay_live_and_an_idle_one_expires(conn, org):
    (cred, player), _ = phone(conn, org)
    toks = []
    for _ in range(4):
        toks.append(identity.pair(conn, SECRET, identity.new_guest_code(conn, SECRET, player["id"], cred["id"])["pairing_code"], "iPad")["credential"])
    live = [t for t in toks if identity.authenticate(conn, SECRET, t)]
    assert len(live) == 3 and toks[0] not in live
    conn.execute("UPDATE credentials SET last_seen_at=? WHERE shared=1", (db.plus(db.now(), hours=-(identity.SHARED_IDLE_HOURS + 1)),))
    assert all(identity.authenticate(conn, SECRET, t) is None for t in toks)


def test_a_coach_can_issue_the_code_and_it_is_audited(conn, org):
    sid = org["coach"][0]
    code = identity.new_guest_code(conn, SECRET, org["p1"], None, sid)["pairing_code"]
    got = identity.pair(conn, SECRET, code, "iPad")
    assert got["shared"] and conn.execute("SELECT COUNT(*) n FROM audit_log WHERE action IN ('guest_code_issued','guest_signin')").fetchone()["n"] == 2


def test_the_ordinary_pairing_code_still_retires_the_browser_credential(conn, org):
    (cred, player), tok = phone(conn, org)
    code = identity.new_pairing_code(conn, SECRET, player["id"], cred["id"])["pairing_code"]
    got = identity.pair(conn, SECRET, code, "home screen")
    assert "shared" not in got and identity.authenticate(conn, SECRET, tok) is None


def test_an_older_database_gains_the_new_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    c0 = sqlite3.connect(path)
    c0.executescript("CREATE TABLE schema_version(version INTEGER NOT NULL); INSERT INTO schema_version VALUES (1);"
                     "CREATE TABLE players(id INTEGER PRIMARY KEY, org_id TEXT, mlbam_id INTEGER, name TEXT NOT NULL, bats TEXT NOT NULL, throws TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT '');"
                     "CREATE TABLE credentials(id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL, token_hash TEXT NOT NULL UNIQUE, label TEXT, created_at TEXT NOT NULL, last_seen_at TEXT, revoked_at TEXT, revoked_reason TEXT, via TEXT NOT NULL);"
                     "CREATE TABLE codes(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, player_id INTEGER NOT NULL, code_hash TEXT NOT NULL UNIQUE, from_credential_id INTEGER, created_by INTEGER, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, revoked_at TEXT);")
    c0.commit()
    c0.close()
    c = db.connect(path)
    db.migrate(c)
    assert "shared" in [r["name"] for r in c.execute("PRAGMA table_info(credentials)")] and "keep_issuer" in [r["name"] for r in c.execute("PRAGMA table_info(codes)")]
    assert c.execute("SELECT MAX(version) v FROM schema_version").fetchone()["v"] == db.SCHEMA_VERSION
