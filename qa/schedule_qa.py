"""Browser QA for the weekly slate: an admin and a coach in real browsers (Chromium or WebKit) typing into the grid, pressing every button, and a hitter's phone showing the result.

  PYTHONPATH=src python3 qa/schedule_qa.py [--engine chromium|webkit] [--only S1,S4]

Each check starts from a new empty database, so none leans on another.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
import time
import traceback

os.environ["ENGINE_CONSENT_FILE"] = "/nonexistent/consent.json"
import uvicorn  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gameplan.engine import app as engine_app, db, identity, runner, schedule  # noqa: E402

SECRET = "qa-secret-not-for-production-use"
ADMIN = "qa-admin-token-at-least-24-chars"
CHROME = "/opt/pw-browsers/chromium-1234/chrome-linux64/chrome"
ARGS: dict = {}
RESULTS: list = []


def check(tid, desc):
    def deco(fn):
        if ARGS.get("only") and not any(tid == x for x in ARGS["only"]):
            return fn
        t0 = time.time()
        try:
            ev = fn()
            RESULTS.append(dict(id=tid, test=desc, result="PASS", evidence=str(ev or ""), seconds=round(time.time() - t0, 1)))
        except AssertionError as e:
            RESULTS.append(dict(id=tid, test=desc, result="FAIL", evidence=str(e)[:500], seconds=round(time.time() - t0, 1)))
        except Exception as e:
            RESULTS.append(dict(id=tid, test=desc, result="FAIL", evidence=f"{type(e).__name__}: {str(e)[:300]}", seconds=round(time.time() - t0, 1), trace=traceback.format_exc()[-700:]))
        print(f"{RESULTS[-1]['result']:5s} {tid:4s} {desc}" + ("" if RESULTS[-1]["result"] == "PASS" else "  <- " + RESULTS[-1]["evidence"][:240]), flush=True)
        return fn
    return deco


class Server:
    def __init__(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.app = engine_app.create_app(self.dir / "data", SECRET, ADMIN, trust_proxy=False)
        self.srv = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="error", lifespan="off"))
        self.th = threading.Thread(target=self.srv.run, daemon=True)
        self.th.start()
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        self.base = f"http://127.0.0.1:{self.port}"
        self.c = db.connect(self.app.state.ctx.db_path)
        self.t1 = identity.add_team(self.c, "Visalia Rawhide", "Single-A", 516, 14, "tracking_drawn")
        self.t2 = identity.add_team(self.c, "Reno Aces", "Triple-A", 2310, 11, "tracking_drawn")
        self.p1 = identity.add_player(self.c, "Jordan Smith", "L", self.t1, "ORG-1")
        identity.add_player(self.c, "Alex Jones", "R", self.t1, "ORG-2")
        identity.add_player(self.c, "Sam Lee", "R", self.t2, "ORG-3")
        self.coach = identity.create_staff(self.c, SECRET, "Coach V", "coach", [self.t1])[1]

    def rows(self, sql, *a):
        return [dict(r) for r in self.c.execute(sql, a)]

    def stop(self):
        self.srv.should_exit = True
        self.th.join(5)
        self.c.close()


def signin(p, S, token):
    p.goto(S.base + "/staff/login")
    p.fill("input[name=token]", token)
    p.click("button.pri")
    p.wait_for_url("**/staff")


def tomorrow(n=1):
    return (dt.date.fromisoformat(db.local_today()) + dt.timedelta(days=n)).isoformat()


def fill_cell(p, tid, date, name=None, pid=None, opp=None, game=1):
    k = f"{tid}|{date}|{game}"
    for pre, v in (("n", name), ("i", pid), ("o", opp)):
        if v is not None:
            p.fill(f'input[name="{pre}_{k}"]', v)


def save(p):
    p.click("text=Save the week")
    p.wait_for_load_state("networkidle")


def main():
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["chromium", "webkit"], default="chromium")
    ap.add_argument("--only", default="")
    ARGS.update(engine=ap.parse_args().engine, only=[x for x in ap.parse_args().only.split(",") if x])
    with sync_playwright() as pw:
        b = pw.webkit.launch() if ARGS["engine"] == "webkit" else pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        errors: list = []

        def page(w=1280, h=900, mobile=False):
            ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, service_workers="block")
            p = ctx.new_page()
            p.on("pageerror", lambda e: errors.append(str(e)))
            return ctx, p

        @check("S1", "Admin types a starter into the grid, presses Save, and it is stored for exactly that affiliate and date")
        def _():
            S = Server()
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + f"/staff/schedule?start={tomorrow()}")
            fill_cell(p, S.t1, tomorrow(), "Ace One", "101", "Modesto")
            fill_cell(p, S.t2, tomorrow(2), "Reno Ace", "201", "Tacoma")
            save(p)
            assert "Saved 2" in p.inner_text(".flash"), p.inner_text("main")[:300]
            rows = S.rows("SELECT team_id, game_date, pitcher_name, pitcher_id, opponent, status FROM starters ORDER BY team_id")
            ctx.close()
            S.stop()
            assert rows == [dict(team_id=S.t1, game_date=tomorrow(), pitcher_name="Ace One", pitcher_id=101, opponent="Modesto", status="confirmed"),
                            dict(team_id=S.t2, game_date=tomorrow(2), pitcher_name="Reno Ace", pitcher_id=201, opponent="Tacoma", status="confirmed")], rows
            return "two boxes, two rows, right team and date each"

        @check("S2", "Saving the same week again says unchanged and queues nothing new")
        def _():
            S = Server()
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + f"/staff/schedule?start={tomorrow()}")
            fill_cell(p, S.t1, tomorrow(), "Ace One", "101")
            save(p)
            first = S.rows("SELECT id, confirmed_at FROM starters")
            save(p)
            msg = p.inner_text(".flash")
            after = S.rows("SELECT id, confirmed_at FROM starters")
            ctx.close()
            S.stop()
            assert "unchanged 1" in msg and first == after, (msg, first, after)
            return msg

        @check("S3", "A bad id saves nothing at all, names the problem, and keeps every box as typed")
        def _():
            S = Server()
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + f"/staff/schedule?start={tomorrow()}")
            fill_cell(p, S.t1, tomorrow(1), "Good Guy", "101")
            fill_cell(p, S.t1, tomorrow(2), "Bad Id Guy", "12x")
            save(p)
            txt = p.inner_text("main")
            kept = p.input_value(f'input[name="n_{S.t1}|{tomorrow(1)}|1"]'), p.input_value(f'input[name="i_{S.t1}|{tomorrow(2)}|1"]')
            n = len(S.rows("SELECT id FROM starters"))
            ctx.close()
            S.stop()
            assert "Nothing was saved" in txt and "digits only" in txt and n == 0 and kept == ("Good Guy", "12x"), (txt[:300], n, kept)
            return "400 page, 0 rows, inputs kept"

        @check("S4", "Doubleheader: the + doubleheader control opens game 2 and both games are saved in order")
        def _():
            S = Server()
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + f"/staff/schedule?start={tomorrow()}")
            p.click("summary:has-text('doubleheader') >> nth=0")
            fill_cell(p, S.t1, tomorrow(), "Game One", "1", game=1)
            fill_cell(p, S.t1, tomorrow(), "Game Two", "2", game=2)
            save(p)
            rows = S.rows("SELECT game_no, pitcher_name FROM starters WHERE team_id=? ORDER BY game_no", S.t1)
            ctx.close()
            S.stop()
            assert rows == [dict(game_no=1, pitcher_name="Game One"), dict(game_no=2, pitcher_name="Game Two")], rows
            return "game 1 and game 2 stored"

        @check("S5", "Replace and clear: a changed box supersedes the old starter, a ticked clear box removes it, a blanked box does not")
        def _():
            S = Server()
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + f"/staff/schedule?start={tomorrow()}")
            fill_cell(p, S.t1, tomorrow(1), "Ace One", "101")
            fill_cell(p, S.t1, tomorrow(2), "Ace Two", "102")
            fill_cell(p, S.t1, tomorrow(3), "Ace Three", "103")
            save(p)
            fill_cell(p, S.t1, tomorrow(1), "Replacement", "111")
            p.check(f'input[name="x_{S.t1}|{tomorrow(2)}|1"]')
            fill_cell(p, S.t1, tomorrow(3), "", "", "")
            save(p)
            live = S.rows("SELECT game_date, pitcher_name FROM starters WHERE status='confirmed' ORDER BY game_date")
            ctx.close()
            S.stop()
            assert live == [dict(game_date=tomorrow(1), pitcher_name="Replacement"), dict(game_date=tomorrow(3), pitcher_name="Ace Three")], live
            return "replaced, cleared, and the blanked box left alone"

        @check("S6", "Rain delay: Hold keeps tonight's starter for the hitter, shows HELD, and Back to the clock lifts it; Show the next game now switches him early")
        def _():
            S = Server()
            sd = schedule.slate_day(S.c, S.t1)["date"]
            nxt = (dt.date.fromisoformat(sd) + dt.timedelta(days=1)).isoformat()
            schedule.set_entry(S.c, S.t1, sd, "Tonight Ace", 1, "Opp A")
            schedule.set_entry(S.c, S.t1, nxt, "Tomorrow Ace", 2, "Opp B")
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + "/staff/schedule")
            assert "Tonight Ace" in p.inner_text("main")
            p.click("summary:has-text('change') >> nth=0")
            from zoneinfo import ZoneInfo
            later = (dt.datetime.now(ZoneInfo("America/Los_Angeles")) + dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
            p.fill("input[name=until]", later)
            p.fill("input[name=reason]", "rain delay")
            p.click("button:has-text('Hold')")
            p.wait_for_load_state("networkidle")
            held = "held" in p.inner_text("main") and "rain delay" in p.inner_text("main")
            holds = S.rows("SELECT pin_date, reason FROM slate_holds WHERE cleared_at IS NULL")
            p.click("summary:has-text('change') >> nth=0")
            p.click("button:has-text('Back to the clock')")
            p.wait_for_load_state("networkidle")
            cleared = not S.rows("SELECT id FROM slate_holds WHERE cleared_at IS NULL")
            p.click("summary:has-text('change') >> nth=0")
            p.click("button:has-text('Show the next game now')")
            p.wait_for_load_state("networkidle")
            adv = schedule.resolve(S.c, S.t1)["entries"][0]["pitcher_name"]
            ctx.close()
            S.stop()
            assert held and holds == [dict(pin_date=sd, reason="rain delay")] and cleared and adv == "Tomorrow Ace", (held, holds, cleared, adv)
            return "held, cleared, advanced"

        @check("S7", "A coach sees only their own affiliate, cannot type into the grid, and gets no Save or hold controls")
        def _():
            S = Server()
            ctx, p = page()
            signin(p, S, S.coach)
            p.goto(S.base + "/staff/schedule")
            txt = p.inner_text("main")
            ro = p.evaluate("[...document.querySelectorAll('input[name^=n_]')].every(i => i.readOnly)")
            ctx.close()
            S.stop()
            assert "Visalia Rawhide" in txt and "Reno Aces" not in txt and "Save the week" not in txt and "Keep this starter until" not in txt and ro, txt[:300]
            return "read-only"

        @check("S8", "The hitter's phone shows the starter and opponent for tonight, says plainly when it is from a comp, and warns when its list is older than the last switch")
        def _():
            S = Server()
            sd = schedule.slate_day(S.c, S.t1)["date"]
            e = schedule.set_entry(S.c, S.t1, sd, "Tonight Ace", 1, "Modesto")["id"]
            S.c.execute("UPDATE starters SET content_kind='comp', comp_note='Logan Webb' WHERE id=?", (e,))
            tk = identity.create_claim(S.c, SECRET, S.p1)
            ctx, p = page(390, 844, mobile=True)
            p.goto(f"{S.base}/c/{tk}")
            p.wait_for_selector("#gYes", timeout=15000)
            p.click("#gYes")
            p.wait_for_selector(".codebox", timeout=15000)
            p.click("#gGo")
            p.wait_for_function("window.__engine && window.__engine.me() && !document.body.classList.contains('gate') && window.__gonogo.queue()", timeout=15000)
            p.click("#tabs button[data-t=queue]")
            p.wait_for_selector("#slateCard", timeout=10000)
            card = p.inner_text("#slateCard")
            stale_before = p.query_selector("#staleCard") is not None
            p.route("**/api/playlist", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({**json.loads(r.fetch().text()), "slate": {**json.loads(r.fetch().text())["slate"], "valid_until": "2020-01-01T00:00:00.000000Z"}})))
            p.evaluate("document.getElementById('refreshPl') && document.getElementById('refreshPl').click()")
            p.wait_for_selector("#staleCard", timeout=10000)
            ctx.close()
            S.stop()
            assert "Tonight Ace" in card and "Modesto" in card and "Logan Webb" in card and "not the starter" in card and not stale_before
            return card.replace("\n", " | ")

        @check("S9", "Comp finder: a typed arsenal returns right-handed MLB pitchers, Use records the choice, and the grid then labels the game as a comp")
        def _():
            S = Server()
            e = schedule.set_entry(S.c, S.t1, tomorrow(), "Milb Arm", 555)["id"]
            S.c.execute("UPDATE starters SET build_state='no_video', build_detail='history: 0 starts' WHERE id=?", (e,))
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + f"/staff/schedule?start={tomorrow()}")
            assert "no video or tracking found" in p.inner_text("main")
            p.click("text=find a comp")
            p.select_option("select[name=hand]", "R")
            for k, v in dict(rel_z="5.9", rel_x="2.0", ext="6.3", arm_angle="35", t1="FF", u1="55", v1="93", h1="8", i1="16", t2="SL", u2="25", v2="85", h2="3", i2="2", t3="CH", u3="20", v3="86", h3="14", i3="6").items():
                p.fill(f"input[name={k}]", v)
            p.click("button:has-text('Find comps')")
            p.wait_for_selector("text=Closest MLB pitchers")
            n = p.locator("form[action='/staff/comps/use']").count()
            hands = p.inner_text("main").count("RHP")
            p.locator("form[action='/staff/comps/use'] button").first.click()
            p.wait_for_load_state("networkidle")
            grid = p.inner_text("main")
            row = S.rows("SELECT content_kind, comp_note, build_state FROM starters WHERE id=?", e)[0]
            ctx.close()
            S.stop()
            assert n == 8 and hands == 8 and row["content_kind"] == "comp" and row["build_state"] == "queued" and "Using" in grid and row["comp_note"] in grid, (n, hands, row, grid[:200])
            return f"8 right-handed comps, chose {row['comp_note']}"

        @check("S10", "Preview shows each hitter's outcome for tonight and after the next switch, and lists what is wrong before the night")
        def _():
            S = Server()
            ctx, p = page()
            signin(p, S, ADMIN)
            p.goto(S.base + "/staff/schedule/preview")
            now_txt = p.inner_text("main")
            html = p.text_content("main")                               # the hitter list is folded away, so inner_text would skip it
            p.click("text=After the next switch")
            p.wait_for_load_state("networkidle")
            nxt_txt = p.inner_text("main")
            ctx.close()
            S.stop()
            assert "no starter confirmed" in now_txt and "after the next switch" in nxt_txt and "Jordan Smith" in html
            return "empty schedule flagged"

        b.close()
        bad = [r for r in RESULTS if r["result"] != "PASS"]
        print(f"\n{len(RESULTS)} checks, {len(RESULTS) - len(bad)} pass, {len(bad)} fail; page errors: {errors[:3]}")
        pathlib.Path(__file__).with_name(f"results_schedule_{ARGS['engine']}.json").write_text(json.dumps(RESULTS, indent=1))
        sys.exit(1 if bad or errors else 0)


if __name__ == "__main__":
    main()
