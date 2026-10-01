"""The app works end to end: the server lists games, a game opens from the library, a skip is saved by the server and survives a
reload, and an unbuilt game offers a Build button. Uses a real server on a free port and a real browser."""
import json
import pathlib
import socket
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).parent.parent
CHROMIUM = "/opt/pw-browsers/chromium"
pw = pytest.importorskip("playwright.sync_api")
GAME = ROOT / "docs" / "gameview2" / "game.json"


@pytest.fixture()
def server(tmp_path):
    from gameplan.server import App, make_handler

    league = tmp_path / "league"
    league.mkdir()
    head = "game_pk,pitcher,inning_topbot,at_bat_number,home_team,away_team\n"
    (league / "2025-09-07.csv").write_text(head + "900001,111,Top,1,SEA,TEX\n900001,222,Bot,2,SEA,TEX\n900001,111,Top,3,SEA,TEX\n")
    app = App(str(league), str(tmp_path / "app"), None)
    app.build_index()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", app
    srv.shutdown()


@pytest.mark.skipif(not pathlib.Path(CHROMIUM).exists() or not GAME.exists(), reason="no browser or demo game")
def test_library_open_skip_persist(server):
    url, app = server
    games = json.load(urllib.request.urlopen(url + "/api/games"))["games"]
    by = {g["game_pk"]: g for g in games}
    assert by["900001"]["status"] == "new" and by["900001"]["home"] == "SEA" and by["900001"]["pas"] == 3
    pk = json.load(open(GAME))["game_pk"]
    assert by[pk]["status"] == "ready"

    errors = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/")
        pg.wait_for_selector(".grow")
        pg.select_option("#libdate", "")                                   # all dates
        assert pg.query_selector("[data-build='900001']") is not None      # unbuilt game offers Build
        pg.fill("#libq", "BOS")
        pg.click(f"[data-open='{pk}']")
        pg.wait_for_selector(".hero")                                      # game page
        assert pg.url.endswith(f"#/game/{pk}")
        assert "BOS at ARI" in pg.inner_text("#title")
        # every game tab loads from the library route
        for v in ("board", "hitters", "log", "game"):
            pg.click(f"[data-v={v}]")
            assert "undefined" not in pg.inner_text("#main") and "NaN" not in pg.inner_text("#main")
        # skip a plate appearance, then confirm the server stored it and a reload still shows it
        pg.click("[data-pa]")
        pg.click("[data-skip]")
        pg.wait_for_timeout(600)
        log = json.load(urllib.request.urlopen(url + "/api/log"))
        assert any(v.get("path") == "SKIP" for v in log.values())
        pg.reload()
        pg.wait_for_selector(".hero")
        assert pg.query_selector(".pa.skip") is not None
        # back to the library
        pg.click("[data-v=library]")
        pg.wait_for_selector(".grow")
        b.close()
    assert not errors, errors[:3]


@pytest.mark.skipif(not pathlib.Path(CHROMIUM).exists() or not GAME.exists(), reason="no browser or demo game")
def test_pending_board_loads_when_ready(server):
    """A game opens before its boards exist; the Pregame tab waits, then shows the board once the server has it."""
    url, app = server
    g = json.load(open(GAME))
    pk = "900002"
    g["game_pk"] = pk
    full = {h["id"]: h for sd in g["sides"].values() for h in sd["board"]["hitters"]}
    for sd in g["sides"].values():                                  # skeleton boards, as a lazy build writes them
        sd["board"]["hitters"] = [{"order": h["order"], "id": h["id"], "name": h["name"], "stand": h["stand"], "pending": True}
                                  for h in sd["board"]["hitters"]]
    d = app.games_dir / pk
    (d / "boards").mkdir(parents=True)
    (d / "game.json").write_text(json.dumps(g))
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + f"/#/game/{pk}")
        pg.wait_for_selector(".hero")
        pg.click("[data-v=board]")
        pg.wait_for_selector("text=still being built")
        first = g["sides"]["Top"]["board"]["hitters"][0]["id"]
        (d / "boards" / f"{first}.json").write_text(json.dumps(full[first]))      # the build finishes this hitter
        pg.wait_for_selector("text=Value plan", timeout=15000)
        assert not errors, errors[:3]
        b.close()
