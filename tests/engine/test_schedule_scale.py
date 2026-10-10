"""Eighty-odd hitters on six affiliates, the whole season's schedule entered, and every phone opening the app in the same minute the starter flips."""
import concurrent.futures as cf
import time

from fastapi.testclient import TestClient

from gameplan.engine import app as engine_app
from gameplan.engine import db, identity, packs, playlist, schedule

from .test_answers_playlist import item

SECRET = "test-secret-not-for-production"
ADMIN = "admin-token-at-least-24-characters-long"
FLIP = "2027-05-05T04:00:00.000000Z"            # 21:00 Pacific


def build_org(c, tmp, n_teams=6, per_team=14, nights=14):
    out = []
    for ti in range(n_teams):
        t = identity.add_team(c, f"Team {ti}", "A", 100 + ti, 14, "tracking_drawn")
        pids = [identity.add_player(c, f"T{ti} Hitter {i}", "SLR"[i % 3], t, f"ORG-{ti}-{i}") for i in range(per_team)]
        for n in range(nights):
            d = f"2027-05-{4 + n:02d}"
            e = schedule.set_entry(c, t, d, f"T{ti} Starter {n}", 1000 * ti + n + 1)["id"]
            for side in "LR":
                its = [item(f"i{ti}_{n}_{side}{k}", strike=bool(k % 2), pt="FF", stand=side) for k in range(8)]
                packs.register(c, dict(id=f"s{ti}_{n}_{side}", dir="p", title=f"T{ti} N{n}", subtitle="", mode="train", items=its), "starter", side, "test", tmp / "content", tmp / "src", t, e, None)
        out.append((t, pids))
    return out


def test_a_whole_org_computes_fast_and_every_hitter_sees_his_own_teams_starter(conn, tmp_path):
    org = build_org(conn, tmp_path)
    assert sum(len(p) for _, p in org) == 84
    t0 = time.time()
    for t, pids in org:
        for pid in pids:
            p = conn.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
            pl = playlist.compose(conn, p, now_iso=FLIP)
            idx = org.index((t, pids))
            assert [g["starter"] for g in pl["slate"]["games"]] == [f"T{idx} Starter 1"], (idx, pl["slate"]["games"])
            assert pl["packs"] and all(m["title"] == f"T{idx} N1" for m in pl["packs"]), pl["notes"]
    dt = time.time() - t0
    assert dt < 8, dt                                               # 84 playlists written, generous bound for a slow runner
    t0 = time.time()
    out = schedule.preview(conn, None, FLIP)
    assert time.time() - t0 < 8 and all(not o["problems"] for o in out), [o["problems"] for o in out if o["problems"]]


def test_everyone_opens_the_app_in_the_minute_it_flips(tmp_path):
    app = engine_app.create_app(tmp_path / "data", SECRET, ADMIN, trust_proxy=False)
    c = db.connect(app.state.ctx.db_path)
    org = build_org(c, tmp_path, n_teams=3, per_team=12, nights=6)
    creds = []
    for t, pids in org:
        for pid in pids:
            tok = identity.create_claim(c, SECRET, pid)
            creds.append((t, identity.claim_confirm(c, SECRET, tok, "x")["credential"]))
    import gameplan.engine.db as _db
    real = _db.now
    _db.now = lambda: FLIP                                          # the server's clock reads the flip for every request
    try:
        def one(a):
            t, cred = a
            r = TestClient(app).get("/api/playlist", headers={"Authorization": f"Bearer {cred}"})
            return t, r.status_code, [g["starter"] for g in r.json()["slate"]["games"]]
        with cf.ThreadPoolExecutor(24) as ex:
            res = list(ex.map(one, creds))
    finally:
        _db.now = real
    assert len(res) == 36 and all(code == 200 for _, code, _ in res)
    team_idx = {t: i for i, (t, _) in enumerate(org)}
    assert all(names == [f"T{team_idx[t]} Starter 1"] for t, _, names in res)
    c.close()
