import json

from gameplan import next_starter as NS
from gameplan import prepare as PR


def sched(games):
    return {"dates": [{"date": d, "games": [g]} for d, g in games]}


def game(pk, when, state, home_id, away_id, away_pp=None, home_pp=None, season="2026"):
    t = lambda i, pp: {"team": {"id": i, "name": f"T{i}"}, **({"probablePitcher": {"id": pp, "fullName": f"P{pp}"}} if pp else {})}
    return (when[:10], {"gamePk": pk, "gameDate": when, "season": season, "status": {"abstractGameState": state}, "teams": {"home": t(home_id, home_pp), "away": t(away_id, away_pp)}})


def test_confirmed_picks_the_first_unfinished_game_and_the_opponents_pitcher():
    d = sched([game(1, "2026-04-09T23:00:00Z", "Final", 109, 5, away_pp=99), game(2, "2026-04-10T23:00:00Z", "Preview", 109, 5, away_pp=77, home_pp=11), game(3, "2026-04-11T23:00:00Z", "Preview", 109, 5, away_pp=78)])
    r = NS.resolve(109, "2026-04-09", fetch=lambda url: d)
    assert (r["status"], r["game_pk"], r["pitcher_id"], r["we_are"], r["opponent_id"]) == ("confirmed", 2, 77, "home", 5)     # not our own pitcher 11, not the finished game


def test_away_game_reads_the_home_pitcher():
    d = sched([game(2, "2026-04-10T23:00:00Z", "Preview", 5, 109, away_pp=11, home_pp=66)])
    r = NS.resolve(109, "2026-04-10", fetch=lambda url: d)
    assert r["pitcher_id"] == 66 and r["we_are"] == "away"


def test_tbd_and_no_game_are_reported_not_guessed():
    d = sched([game(2, "2026-04-10T23:00:00Z", "Preview", 109, 5, home_pp=11)])
    assert NS.resolve(109, "2026-04-10", fetch=lambda url: d)["status"] == "tbd"
    assert NS.resolve(109, "2026-04-10", fetch=lambda url: sched([game(1, "2026-04-10T23:00:00Z", "Final", 109, 5)]))["status"] == "no_game"


def test_prepare_refuses_to_build_without_a_confirmed_starter(tmp_path):
    called = []
    r = PR.prepare(109, "2026-04-10", tmp_path, tmp_path, resolver=lambda t, o: dict(status="tbd"), builder=lambda *a, **k: called.append(1))
    assert not r["ok"] and not r["built"] and not called and r["gates"][0]["gate"] == "starter_confirmed"


def item(i, strike=True, pt="FF", ars=("FF", "SL"), key=True, pocket="mid-mid"):
    return dict(id=i, file=f"{i}.mp4", release=1.6, keys=dict(strike=strike, pitch_type=pt) if key else None, arsenal=list(ars), meta=dict(pitch_type=pt, pocket=pocket))


def test_key_and_choice_gates_catch_the_specific_failure():
    q = dict(packs=[dict(id="s", mode="train", items=[item("a"), item("b", pt="CH")]), dict(id="a", mode="assess", items=[item("c", key=True), item("d", key=False)])])
    out = {g["gate"]: g for g in PR.check_keys_and_choices(q, {"a/d": {}}, "R")}
    assert out["answer_keys"]["status"] == "FAIL" and any("key shipped" in x for x in out["answer_keys"]["detail"]) and any("no private key" in x for x in out["answer_keys"]["detail"])
    assert out["choices"]["status"] == "FAIL" and "CH" in out["choices"]["detail"][0]            # CH thrown but not among FF/SL
    ok = dict(packs=[dict(id="s", mode="train", items=[item("a"), item("b", pt="SL", strike=False)]), dict(id="a", mode="assess", items=[item("d", key=False)])])
    assert all(g["status"] == "PASS" for g in PR.check_keys_and_choices(ok, {"a/d": {}}, "R"))


def test_file_gate_fails_short_or_missing_clips(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "a.mp4").write_bytes(b"x" * 20000)
    (tmp_path / "p" / "b.mp4").write_bytes(b"x" * 20000)
    q = dict(packs=[dict(id="p", dir="p", mode="train", items=[item("a"), item("b"), item("c")])])
    g = PR.check_pack_files(tmp_path, q, "R", dur=lambda f: 1.8 if f.name == "a.mp4" else 3.0)[0]
    assert g["status"] == "FAIL" and len(g["detail"]) == 2             # a is only 0.2 s past release, c is missing
    assert PR.check_pack_files(tmp_path, dict(packs=[dict(id="p", dir="p", mode="train", items=[item("b")])]), "R", dur=lambda f: 3.0)[0]["status"] == "PASS"


def test_edge_rows_alternate_inside_and_outside_and_exclude_far_pitches():
    import random

    from gameplan import app_content as AC
    mk = lambda i, px, stand="R": dict(play_id=f"p{i}", plateTime=0.4, px=px, pz=2.5, sz_top=3.5, sz_bot=1.5, stand=stand)
    pool = [mk(1, 0.80), mk(2, 0.70), mk(3, 0.90), mk(4, 0.95), mk(5, 0.0), mk(6, 1.5), mk(7, 0.85, "L")]    # 5 is dead center, 6 is far outside, 7 is the other side
    r = AC.edge_rows(pool, "R", random.Random(1))
    assert {p["play_id"] for p in r} == {"p1", "p2", "p3", "p4"}
    inside = [p["px"] <= 0.83 for p in r]
    assert inside[0] != inside[1] and inside[2] != inside[3] and inside.count(True) == 2     # strictly alternating, two of each


def test_edges_gate_needs_both_strikes_and_balls():
    mkq = lambda ks: dict(packs=[dict(id="starter_1_R", mode="train", items=[item("a")]), dict(id="edges_1_R", mode="train", items=[item(str(i), strike=k) for i, k in enumerate(ks)])])
    g = lambda ks: [x for x in PR.check_coverage_and_fit(mkq(ks), [], "R") if x["gate"] == "edges"][0]["status"]
    assert g([True] * 6) == "FAIL" and g([True, False] * 3) == "PASS" and g([True, False] * 2) == "WARN"
