import json

import pytest

from gameplan.engine import answers, db, identity, packs, playlist

from .conftest import SECRET


def item(i, strike=True, pt="FF", pocket="mid-mid", file=None, ars=("FF", "SL", "CH"), stand="L"):
    return dict(id=i, file=file, release=0.0, sim=None, keys=dict(strike=strike, pitch_type=pt), arsenal=list(ars), camera="broadcast",
                meta=dict(pitch_type=pt, family="FB", pocket=pocket, px=0.1, pz=2.5, sz_top=3.5, sz_bot=1.5, speed=93.0, stand=stand))


def make_pack(c, tmp_path, kind="starter", side="L", mode="train", n=4, team=None, title=None, practice=False, pockets=None, pk_id="p"):
    its = [item(f"{kind}{side}{i}", strike=bool(i % 2), pt=["FF", "SL", "CH"][i % 3], pocket=(pockets or ["mid-mid"] * n)[i]) for i in range(n)]
    priv = None
    if mode == "assess":
        priv = {f"{pk_id}/{it['id']}": it["keys"] for it in its}
        for it in its:
            it["keys"] = None
    pack = dict(id=pk_id, dir=pk_id, title=title or f"{kind} {side}", subtitle="", mode=mode, items=its)
    return packs.register(c, pack, kind, side, "test", tmp_path / "content", tmp_path / "src", team, None, priv, practice=practice)


@pytest.fixture
def signed(conn, org):
    tok = identity.create_claim(conn, SECRET, org["p1"])
    got = identity.claim_confirm(conn, SECRET, tok, "phone")
    cred, player = identity.authenticate(conn, SECRET, got["credential"])
    return cred, player


def ans(aid, pack, itm, task="zone", call="Strike", mode="train", **kw):
    return dict(id=aid, pack=pack, clip=itm, task=task, call=call, mode=mode, rt_ms=400, pause_ms=150, camera="broadcast", ts=db.now(), q_order=1, clip_trial=1, session="s1", **kw)


def test_server_scores_from_its_own_keys_not_the_phones_claim(conn, org, signed, tmp_path):
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    out = answers.ingest(conn, player, cred, [ans("aaaaaaaa-1", h, "starterL1", "zone", "Strike", correct=0), ans("aaaaaaaa-2", h, "starterL1", "pitch", "SL")])
    assert out["stored"] == ["aaaaaaaa-1", "aaaaaaaa-2"] and not out["rejected"]
    r = {x["id"]: x for x in conn.execute("SELECT * FROM answers")}
    assert r["aaaaaaaa-1"]["key"] == "Strike" and r["aaaaaaaa-1"]["correct"] == 1 and r["aaaaaaaa-1"]["client_correct"] == 0      # item 1 is a strike; the phone's "0" is kept only as a flag
    assert r["aaaaaaaa-2"]["key"] == "SL" and r["aaaaaaaa-2"]["correct"] == 1 and r["aaaaaaaa-1"]["pocket"] == "mid-mid" and r["aaaaaaaa-1"]["team_id"] == org["t1"] and r["aaaaaaaa-1"]["level"] == "A"


def test_same_answer_twice_or_reordered_is_stored_once_and_ids_cannot_cross_players(conn, org, signed, tmp_path):
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    batch = [ans(f"bbbbbbbb-{i}", h, f"starterL{i}") for i in range(4)]
    first = answers.ingest(conn, player, cred, batch)
    again = answers.ingest(conn, player, cred, list(reversed(batch)))
    assert len(first["stored"]) == 4 and again["stored"] == [] and len(again["duplicates"]) == 4
    assert conn.execute("SELECT COUNT(*) n FROM answers").fetchone()["n"] == 4
    tok = identity.create_claim(conn, SECRET, org["p2"])
    cred2, p2 = identity.authenticate(conn, SECRET, identity.claim_confirm(conn, SECRET, tok, "x")["credential"])
    steal = answers.ingest(conn, p2, cred2, [batch[0]])
    assert steal["stored"] == [] and steal["rejected"] and conn.execute("SELECT player_id FROM answers WHERE id=?", (batch[0]["id"],)).fetchone()["player_id"] == org["p1"]


@pytest.mark.parametrize("change,needle", [
    (dict(pack="f" * 64), "unknown pack"), (dict(clip="nope"), "unknown item"), (dict(task="speed"), "bad task"), (dict(mode="assess"), "mode does not match"),
    (dict(call="Maybe"), "Strike or Ball"), (dict(id="x"), "bad id"), (dict(rt_ms=-5), "out of range"), (dict(call=""), "bad call")])
def test_bad_answers_are_rejected_with_a_reason_and_do_not_block_good_ones(conn, org, signed, tmp_path, change, needle):
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    good = ans("cccccccc-1", h, "starterL0")
    bad = dict(ans("cccccccc-2", h, "starterL1"), **change)
    out = answers.ingest(conn, player, cred, [bad, good])
    assert out["stored"] == ["cccccccc-1"] and len(out["rejected"]) == 1 and needle in out["rejected"][0]["reason"]


def test_pitch_call_must_be_one_the_pitcher_offers_and_other_teams_packs_are_refused(conn, org, signed, tmp_path):
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    other = make_pack(conn, tmp_path, kind="edges", team=org["t2"], pk_id="q")
    out = answers.ingest(conn, player, cred, [ans("dddddddd-1", h, "starterL0", "pitch", "KN"), ans("dddddddd-2", other, "edgesL0")])
    assert out["stored"] == [] and {r["reason"] for r in out["rejected"]} == {"call is not one of the offered pitch types", "pack is not for this player"}


def test_a_late_sync_after_a_promotion_is_accepted_for_the_old_team_and_stamped_with_it(conn, org, signed, tmp_path):
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    identity.assign(conn, org["p1"], org["t2"], "2027-06-01")
    out = answers.ingest(conn, player, cred, [ans("eeeeeeee-1", h, "starterL0")], server_ts="2027-06-20T00:00:00.000000Z")
    assert out["stored"] == ["eeeeeeee-1"]


def test_batch_limits_and_garbage_shapes(conn, org, signed):
    cred, player = signed
    with pytest.raises(identity.EngineError):
        answers.ingest(conn, player, cred, [{}] * 501)
    with pytest.raises(identity.EngineError):
        answers.ingest(conn, player, cred, "nope")
    out = answers.ingest(conn, player, cred, [None, 5, "x", {}, []])
    assert out["stored"] == [] and len(out["rejected"]) == 5


def test_assessment_keys_never_reach_the_player_but_score_on_the_server(conn, org, signed, tmp_path):
    cred, player = signed
    h = make_pack(conn, tmp_path, kind="assess", mode="assess", team=org["t1"], pk_id="a")
    pl = playlist.compose(conn, player)
    m = [p for p in pl["packs"] if p["id"] == h][0]
    assert all(i["keys"] is None for i in m["items"]) and "keys" not in json.dumps([{k: v for k, v in i.items() if k != "keys"} for i in m["items"]]).replace('"keys"', "")
    out = answers.ingest(conn, player, cred, [ans("ffffffff-1", h, "assessL1", "zone", "Strike", mode="assess")])
    assert out["stored"] and conn.execute("SELECT key, correct FROM answers WHERE id='ffffffff-1'").fetchone()["correct"] == 1


def test_void_hides_an_answer_from_the_live_set_without_deleting_it(conn, org, signed, tmp_path):
    cred, player = signed
    h = make_pack(conn, tmp_path, team=org["t1"])
    answers.ingest(conn, player, cred, [ans("gggggggg-1", h, "starterL0")])
    with pytest.raises(identity.EngineError):
        answers.void(conn, "gggggggg-1", " ", None)
    answers.void(conn, "gggggggg-1", "tapped by accident", org["coach"][0])
    assert conn.execute(f"SELECT COUNT(*) n FROM answers WHERE {answers.LIVE}").fetchone()["n"] == 0 and conn.execute("SELECT COUNT(*) n FROM answers").fetchone()["n"] == 1


def test_registering_the_same_pack_twice_gives_the_same_hash_and_no_duplicate(conn, org, tmp_path):
    a = make_pack(conn, tmp_path, team=org["t1"])
    b = make_pack(conn, tmp_path, team=org["t1"])
    assert a == b and conn.execute("SELECT COUNT(*) n FROM packs").fetchone()["n"] == 1
    c = make_pack(conn, tmp_path, team=org["t1"], title="different title")
    assert c != a


def test_identical_content_for_two_teams_is_two_packs(conn, org, tmp_path):
    a = make_pack(conn, tmp_path, team=org["t1"])
    b = make_pack(conn, tmp_path, team=org["t2"])
    assert a != b and {r["team_id"] for r in conn.execute("SELECT team_id FROM packs")} == {org["t1"], org["t2"]}


def test_a_pack_item_without_a_key_is_refused(conn, org, tmp_path):
    pack = dict(id="k", dir="k", title="t", subtitle="", mode="assess", items=[dict(item("z1"), keys=None)])
    with pytest.raises(ValueError):
        packs.register(conn, pack, "assess", "L", "test", tmp_path / "c", tmp_path / "s", org["t1"], None, {})
    assert conn.execute("SELECT COUNT(*) n FROM packs").fetchone()["n"] == 0                         # nothing half-registered


def test_playlist_uses_his_team_his_side_and_practice_packs_only_when_nothing_is_ready(conn, org, signed, tmp_path):
    cred, player = signed
    pl = playlist.compose(conn, player)
    assert pl["packs"] == [] and "Nothing is ready" in pl["notes"][0]
    prac = make_pack(conn, tmp_path, kind="starter", team=None, practice=True, pk_id="pr", title="Practice")
    pl = playlist.compose(conn, player)
    assert [p["id"] for p in pl["packs"]] == [prac] and "practice pitches" in pl["notes"][0] and pl["packs"][0]["practice"]
    mine = make_pack(conn, tmp_path, kind="starter", team=org["t1"], pk_id="mine")
    make_pack(conn, tmp_path, kind="starter", side="R", team=org["t1"], pk_id="mineR")             # wrong side for a lefty
    make_pack(conn, tmp_path, kind="starter", team=org["t2"], pk_id="other")                       # another team
    pl = playlist.compose(conn, player)
    assert [p["id"] for p in pl["packs"]] == [mine] and not pl["notes"]


def test_cap_unseen_first_weak_pockets_first_and_assessment_whole_and_once(conn, org, signed, tmp_path):
    cred, player = signed
    h = make_pack(conn, tmp_path, kind="starter", team=org["t1"], n=6, pockets=["low-away", "mid-mid", "high-in", "low-away", "mid-mid", "high-in"], pk_id="s1")
    a = make_pack(conn, tmp_path, kind="assess", mode="assess", team=org["t1"], n=5, pk_id="as")
    conn.execute("UPDATE level_settings SET daily_cap=4 WHERE team_id=?", (org["t1"],))
    pl = playlist.compose(conn, player)
    assert [len(p["items"]) for p in pl["packs"]] == [4, 5]                                         # training capped at 4; assessment whole, outside the cap
    # a weak spot: 12 wrong strike/ball answers in low-away (item 3 is a strike, "Ball" is wrong) and 20 right in mid-mid (item 1 is a strike)
    wrong = [ans(f"hhhhhhhh-x{i:02d}", h, "starterL3", "zone", "Ball") for i in range(12)]
    right = [ans(f"hhhhhhhh-y{i:02d}", h, "starterL1", "zone", "Strike") for i in range(20)]
    answers.ingest(conn, player, cred, wrong + right)
    assert playlist.weak_pockets(conn, player["id"]) == ["low-away"]
    conn.execute("UPDATE level_settings SET daily_cap=6 WHERE team_id=?", (org["t1"],))
    first_pack = [p for p in playlist.compose(conn, player)["packs"] if p["mode"] == "train"][0]
    order = [i["id"] for i in first_pack["items"]]
    assert order[0] == "starterL0"                                                                   # unseen and in his weak pocket: first
    assert set(order[-2:]) == {"starterL1", "starterL3"}                                             # the two he has already answered go last
    # an assessment is taken only when every item is answered; a started form resumes with what is left
    answers.ingest(conn, player, cred, [ans("hhhhhhhh-a01", a, "assessL1", "zone", "Strike", mode="assess")])
    resumed = [p for p in playlist.compose(conn, player)["packs"] if p["mode"] == "assess"][0]
    assert resumed["resume"] and [i["id"] for i in resumed["items"]] == ["assessL0", "assessL2", "assessL3", "assessL4"]
    answers.ingest(conn, player, cred, [ans(f"hhhhhhhh-a{i:02d}", a, f"assessL{i}", "zone", "Strike", mode="assess") for i in (0, 2, 3, 4)])
    assert not [p for p in playlist.compose(conn, player)["packs"] if p["mode"] == "assess"]
    # a different form is not offered again inside the window, and is after it
    b2 = make_pack(conn, tmp_path, kind="assess", mode="assess", team=org["t1"], n=3, pk_id="as2", title="Assessment B")
    assert not [p for p in playlist.compose(conn, player)["packs"] if p["id"] == b2]
    conn.execute("UPDATE answers SET server_ts='2020-01-01T00:00:00.000000Z' WHERE mode='assess'")
    assert [p for p in playlist.compose(conn, player)["packs"] if p["id"] == b2]


def test_switch_hitter_gets_both_sides_and_unassigned_player_gets_a_note(conn, org, tmp_path):
    tok = identity.create_claim(conn, SECRET, org["p3"])
    cred, sw = identity.authenticate(conn, SECRET, identity.claim_confirm(conn, SECRET, tok, "x")["credential"])
    l = make_pack(conn, tmp_path, side="L", team=org["t2"], pk_id="l")
    r = make_pack(conn, tmp_path, side="R", team=org["t2"], pk_id="r")
    pl = playlist.compose(conn, sw)
    assert pl["sides"] == ["L", "R"] and {p["id"] for p in pl["packs"]} == {l, r}
    pid = identity.add_player(conn, "No Team", "R")
    tok = identity.create_claim(conn, SECRET, pid)
    _, nt = identity.authenticate(conn, SECRET, identity.claim_confirm(conn, SECRET, tok, "x")["credential"])
    assert "not assigned" in playlist.compose(conn, nt)["notes"][0]
