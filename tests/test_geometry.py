"""Location correctness: the numbers in each game file match the raw pitch rows, and the drawn dots, zone outline and plate sit
exactly where those numbers say, in both zone views. Skipped when the raw day files are not on disk."""
import csv
import glob
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent
GAMES = sorted(glob.glob(str(ROOT / "docs" / "gameview*" / "game.json")))
CHROMIUM = "/opt/pw-browsers/chromium"


def raw_rows(g):
    f = ROOT / "data" / "league" / f"{g['date']}.csv"
    if not f.exists():
        pytest.skip("raw day file not available")
    return {(int(r["at_bat_number"]), int(r["pitch_number"])): r
            for r in csv.DictReader(open(f, encoding="utf-8-sig")) if r["game_pk"] == g["game_pk"]}


@pytest.mark.parametrize("path", GAMES)
def test_pitch_numbers_match_raw_rows(path):
    g = json.load(open(path, encoding="utf-8"))
    raw = raw_rows(g)
    n = 0
    for p in g["pas"]:
        stands = {r["stand"] for (a, _), r in raw.items() if a == p["id"]}
        assert p["stand"] in stands, (p["id"], p["stand"], stands)          # the side he actually batted from in this plate appearance
        for q in p["pitches"]:
            if "x" not in q:
                continue
            r = raw[(p["id"], q["n"])]
            plate_x = float(r["plate_x"])
            away = plate_x if r["stand"] == "R" else -plate_x                # + = away from the batter
            assert abs(q["x"] - away) < 0.006, (p["id"], q["n"], q["x"], away)
            assert abs(q["z"] - float(r["plate_z"])) < 0.006
            assert abs(q["sz_top"] - float(r["sz_top"])) < 0.006 and abs(q["sz_bot"] - float(r["sz_bot"])) < 0.006
            n += 1
    assert n > 200


@pytest.mark.parametrize("path", GAMES)
def test_rendered_geometry_matches_numbers(path):
    pw = pytest.importorskip("playwright.sync_api")
    if not pathlib.Path(CHROMIUM).exists():
        pytest.skip("no browser")
    g = json.load(open(path, encoding="utf-8"))
    raw = raw_rows(g)
    page_path = str(pathlib.Path(path).with_name("game.html"))
    checked = 0
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1280, "height": 1000})
        pg.goto("file://" + page_path)
        for view in ("catcher", "batter"):
            pg.select_option("#vside", view)
            for idx, pa in enumerate(g["pas"]):
                if not any("x" in q for q in pa["pitches"]):
                    continue
                pg.query_selector_all("[data-pa]")[idx].click()
                svg = pg.query_selector("svg.zone")
                pts = svg.query_selector_all("g.pt")
                stand = pa["stand"]
                mirror = view == "catcher" and stand == "L"
                for el in pts:
                    n = int(el.get_attribute("data-n"))
                    q = next(x for x in pa["pitches"] if x["n"] == n)
                    r = raw[(pa["id"], n)]
                    # expected from the RAW row, independent of the game file: catcher view draws plate_x as is
                    plate_x, z = float(r["plate_x"]), float(r["plate_z"])
                    away = plate_x if r["stand"] == "R" else -plate_x
                    exp_x = ((-away if mirror else away) + 1.5) * 100
                    if view == "catcher":
                        assert abs(exp_x - (plate_x + 1.5) * 100) < 0.7        # catcher view is the raw plate_x, no flipping
                    exp_y = (4.25 - z) * 100
                    assert abs(float(el.get_attribute("data-cx")) - exp_x) < 0.7, (view, pa["id"], n)
                    assert abs(float(el.get_attribute("data-cy")) - exp_y) < 0.7, (view, pa["id"], n)
                    checked += 1
                # zone outline and plate
                rect = svg.query_selector_all("rect[stroke-width='2.5']")[0]
                top, bot = float(pa["pitches"][0].get("sz_top") or 3.5), float(pa["pitches"][0].get("sz_bot") or 1.5)
                q0 = next((x for x in pa["pitches"] if "x" in x), None)
                top, bot = q0["sz_top"], q0["sz_bot"]
                assert abs(float(rect.get_attribute("y")) - (4.25 - top) * 100) < 0.7
                assert abs(float(rect.get_attribute("height")) - (top - bot) * 100) < 0.7
                assert abs(float(rect.get_attribute("width")) - 166) < 0.01
                assert abs(float(rect.get_attribute("x")) + 0 - (100 * (1.5 - 0.83))) < 0.7        # centered on the plate (x = 0 is 150)
                if idx > 40:
                    break
        b.close()
    assert checked > 150
