import pytest

from gameplan.engine import db, identity, security
from gameplan.engine.identity import EngineError

from .conftest import SECRET


def claim(conn, org, who="p1"):
    tok = identity.create_claim(conn, SECRET, org[who], org["admin"][0])
    return tok, identity.claim_confirm(conn, SECRET, tok, "iPhone")


def test_claim_shows_the_right_person_then_issues_a_credential_and_pairing_code(conn, org):
    tok = identity.create_claim(conn, SECRET, org["p1"], org["admin"][0])
    card = identity.claim_preview(conn, SECRET, tok)
    assert card["name"] == "Jordan Smith" and card["team"] == "Visalia Rawhide" and card["bats"] == "L"
    got = identity.claim_confirm(conn, SECRET, tok, "iPhone")
    assert len(got["credential"]) >= 40 and len(got["pairing_code"]) == 8
    cred, player = identity.authenticate(conn, SECRET, got["credential"])
    assert player["id"] == org["p1"]


def test_secrets_are_stored_only_as_keyed_hashes(conn, org):
    tok, got = claim(conn, org)
    blob = " ".join(str(dict(r)) for t in ("claim_tokens", "credentials", "codes") for r in conn.execute(f"SELECT * FROM {t}"))
    assert tok not in blob and got["credential"] not in blob and got["pairing_code"] not in blob


def test_a_claim_token_works_once_and_a_wrong_or_expired_one_looks_the_same(conn, org):
    tok = identity.create_claim(conn, SECRET, org["p1"])
    identity.claim_confirm(conn, SECRET, tok, "a")
    msgs = set()
    for bad in (tok, "nonsense", "", tok + "x"):
        with pytest.raises(EngineError) as e:
            identity.claim_confirm(conn, SECRET, bad, "b")
        msgs.add((e.value.message, e.value.status))
    assert len(msgs) == 1
    old = identity.create_claim(conn, SECRET, org["p2"])
    conn.execute("UPDATE claim_tokens SET expires_at='2020-01-01T00:00:00.000000Z' WHERE player_id=?", (org["p2"],))
    with pytest.raises(EngineError) as e:
        identity.claim_preview(conn, SECRET, old)
    assert (e.value.message, e.value.status) in msgs


def test_a_new_claim_revokes_the_old_unused_one(conn, org):
    a = identity.create_claim(conn, SECRET, org["p1"])
    b = identity.create_claim(conn, SECRET, org["p1"])
    with pytest.raises(EngineError):
        identity.claim_preview(conn, SECRET, a)
    assert identity.claim_preview(conn, SECRET, b)["id"] == org["p1"]


def test_pairing_gives_the_installed_app_its_own_credential_and_retires_the_browser_one(conn, org):
    _, got = claim(conn, org)
    paired = identity.pair(conn, SECRET, got["pairing_code"].replace("", " ").strip(), "Home Screen app")      # spaces in the code are ignored
    assert identity.authenticate(conn, SECRET, paired["credential"]) is not None
    assert identity.authenticate(conn, SECRET, got["credential"]) is None
    with pytest.raises(EngineError):
        identity.pair(conn, SECRET, got["pairing_code"], "again")                                          # one use only


def test_pairing_code_expires(conn, org):
    _, got = claim(conn, org)
    conn.execute("UPDATE codes SET expires_at='2020-01-01T00:00:00.000000Z'")
    with pytest.raises(EngineError):
        identity.pair(conn, SECRET, got["pairing_code"])


def test_at_most_two_credentials_and_a_third_is_refused(conn, org):
    for _ in range(2):
        tok = identity.create_claim(conn, SECRET, org["p1"])
        identity.claim_confirm(conn, SECRET, tok, "phone")
    tok = identity.create_claim(conn, SECRET, org["p1"])
    with pytest.raises(EngineError) as e:
        identity.claim_confirm(conn, SECRET, tok, "third")
    assert e.value.code == "device_limit"


def test_recovery_retires_every_old_credential_and_works_once(conn, org):
    creds = []
    for _ in range(2):
        tok = identity.create_claim(conn, SECRET, org["p1"])
        creds.append(identity.claim_confirm(conn, SECRET, tok, "phone")["credential"])
    rec = identity.create_recovery(conn, SECRET, org["p1"], org["coach"][0])
    got = identity.recover(conn, SECRET, rec["code"], "new phone")
    assert all(identity.authenticate(conn, SECRET, c) is None for c in creds)
    assert identity.authenticate(conn, SECRET, got["credential"])[1]["id"] == org["p1"]
    with pytest.raises(EngineError):
        identity.recover(conn, SECRET, rec["code"])


def test_one_players_code_cannot_sign_in_another_player(conn, org):
    r1 = identity.create_recovery(conn, SECRET, org["p1"], None)
    r2 = identity.create_recovery(conn, SECRET, org["p2"], None)
    got = identity.recover(conn, SECRET, r2["code"])
    assert identity.authenticate(conn, SECRET, got["credential"])[1]["id"] == org["p2"]
    assert identity.authenticate(conn, SECRET, got["credential"])[1]["id"] != org["p1"]
    assert r1["code"] != r2["code"]


def test_sign_out_and_staff_revoke_end_a_credential(conn, org):
    _, got = claim(conn, org)
    cred, _ = identity.authenticate(conn, SECRET, got["credential"])
    identity.sign_out(conn, cred["id"])
    assert identity.authenticate(conn, SECRET, got["credential"]) is None
    _, got2 = claim(conn, org, "p2")
    cred2, _ = identity.authenticate(conn, SECRET, got2["credential"])
    identity.revoke_credential(conn, cred2["id"], org["admin"][0])
    assert identity.authenticate(conn, SECRET, got2["credential"]) is None


def test_garbage_bearers_are_refused(conn, org):
    for b in (None, "", "x" * 500, "Bearer", "' OR 1=1 --", "\x00"):
        assert identity.authenticate(conn, SECRET, b) is None


def test_promotion_keeps_the_player_and_changes_the_team_from_the_date(conn, org):
    identity.assign(conn, org["p1"], org["t2"], "2027-06-01")
    assert identity.current_assignment(conn, org["p1"], "2027-05-31")["team_id"] == org["t1"]
    assert identity.current_assignment(conn, org["p1"], "2027-06-01")["team_id"] == org["t2"]
    assert identity.current_assignment(conn, org["p1"], "2027-09-01")["level"] == "AAA"
    assert conn.execute("SELECT COUNT(*) n FROM assignments WHERE player_id=?", (org["p1"],)).fetchone()["n"] == 2


def test_roster_import_matches_on_org_id_never_on_name_and_reports_bad_rows(conn, org):
    rows = [dict(name="Jordan Smith", bats="L", team="Reno Aces", org_id="ORG-1"),          # existing id: moved, not duplicated
            dict(name="Jordan Smith", bats="R", team="Visalia Rawhide", org_id="ORG-9"),     # same name, different person
            dict(name="Nobody", bats="X", team="Visalia Rawhide", org_id="ORG-10"),          # bad bats
            dict(name="Lost", bats="L", team="Nowhere", org_id="ORG-11")]                    # bad team
    out = identity.import_roster(conn, rows)
    assert out["added"] == 1 and out["updated"] == 1 and len(out["errors"]) == 2
    assert conn.execute("SELECT COUNT(*) n FROM players WHERE name='Jordan Smith'").fetchone()["n"] == 2
    assert identity.current_assignment(conn, org["p1"])["team_name"] == "Reno Aces"


def test_staff_scope(conn, org):
    coach = identity.authenticate_staff(conn, SECRET, org["coach"][1])
    admin = identity.authenticate_staff(conn, SECRET, org["admin"][1])
    assert identity.staff_team_ids(conn, admin) is None and identity.staff_team_ids(conn, coach) == [org["t1"]]
    assert identity.staff_can_see_player(conn, coach, org["p1"]) and not identity.staff_can_see_player(conn, coach, org["p3"])
    assert identity.authenticate_staff(conn, SECRET, "wrong") is None


def test_every_identity_event_is_audited(conn, org):
    _, got = claim(conn, org)
    identity.pair(conn, SECRET, got["pairing_code"])
    actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log")]
    for a in ("claim_created", "claimed", "paired", "player_added", "staff_created"):
        assert a in actions, a


def test_keyed_hash_depends_on_the_server_secret():
    assert security.keyed_hash("a", "12345678") != security.keyed_hash("b", "12345678")
    assert security.keyed_hash("a", " 1234 ".strip()) == security.keyed_hash("a", "1234")


def test_throttle_blocks_then_recovers():
    t = [0.0]
    th = security.Throttle(3, 10, clock=lambda: t[0])
    assert [th.check("k") for _ in range(4)] == [True, True, True, False]
    t[0] = 11
    assert th.check("k")
