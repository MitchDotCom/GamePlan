"""Release gate for the game viewer: every view of every generated game loads with no script error and no NaN or
undefined on screen. Skipped when playwright or a generated viewer is missing."""
import glob
import pathlib

import pytest

playwright = pytest.importorskip("playwright.sync_api")
CHROMIUM = "/opt/pw-browsers/chromium"
PAGES = sorted(glob.glob(str(pathlib.Path(__file__).parent.parent / "docs" / "gameview*" / "game.html")))
BAD_TEXT = ("NaN", "undefined", "[object Object]", "null%")


@pytest.mark.skipif(not PAGES or not pathlib.Path(CHROMIUM).exists(), reason="no viewer or browser")
@pytest.mark.parametrize("page_path", PAGES)
def test_every_view_renders_clean(page_path):
    errors, bad = [], []
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto("file://" + page_path)

        def check(where):
            text = pg.inner_text("body")
            bad.extend(f"{where}: {t}" for t in BAD_TEXT if t in text)

        for team in pg.eval_on_selector_all("#team option", "o=>o.map(x=>x.value)"):
            pg.select_option("#team", team)
            for pol in ("OFF", "CONTACT_FIRST"):
                pg.select_option("#pol", pol)
                pg.click("[data-v=game]")
                check(f"game {team} {pol}")
                n_pa = len(pg.query_selector_all("[data-pa]"))
                for k in range(n_pa):
                    pg.query_selector_all("[data-pa]")[k].click()
                    check(f"PA {k}")
                    for q in range(len(pg.query_selector_all("[data-pi]"))):
                        pg.query_selector_all("[data-pi]")[q].click()
                        check(f"PA {k} pitch {q}")
        pg.select_option("#team", "all") if pg.query_selector("#team option[value=all]") else None
        pg.click("[data-v=board]")
        hitters = pg.eval_on_selector_all("#bh option", "o=>o.map(x=>x.value)")
        for h in hitters:
            pg.select_option("#bh", h)
            for tto in ("1", "2", "3"):
                pg.click(f"[data-tto='{tto}']")
                for c in [f"{b_}-{s}" for s in range(3) for b_ in range(4)]:
                    pg.click(f"[data-c='{c}']")
                    for k in range(len(pg.query_selector_all("[data-pt]"))):
                        pg.query_selector_all("[data-pt]")[k].click()
                    check(f"board {h} tto{tto} {c}")
        for v in ("hitters", "log"):
            pg.click(f"[data-v={v}]")
            check(v)
        b.close()
    assert not errors, errors[:5]
    assert not bad, bad[:10]
