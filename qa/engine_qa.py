"""End-to-end QA for the engine: a real server, a seeded organization with real clips and drawn pitches, and real browsers (Chromium or WebKit) playing the hitter's part.

  PYTHONPATH=src python3 qa/engine_qa.py [--engine chromium|webkit] [--only E1,E5] [--video DIR --video-keys FILE --drawn DIR --drawn-keys FILE]

Every test starts from a fresh database copy, so tests cannot lean on each other. The guarantees under test are the ones in docs/ENGINE_PLAN.md: the right person, no lost answers, no duplicates,
no answer under the wrong name, recovery from lost storage, and server settings that the phone cannot override.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import traceback

import uvicorn

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from playwright.sync_api import sync_playwright  # noqa: E402

from gameplan.engine import app as engine_app  # noqa: E402
from gameplan.engine import db, identity, seed  # noqa: E402

CHROME = "/opt/pw-browsers/chromium-1234/chrome-linux64/chrome"
SECRET = "qa-secret-qa-secret-qa-secret-1234"
RESULTS: list[dict] = []
ARGS: dict = {}


def check(tid, area, desc, severity="S2"):
    def deco(fn):
        if ARGS.get("only") and not any(tid.startswith(x) for x in ARGS["only"]):
            return fn
        t0 = time.time()
        try:
            ev = fn()
            RESULTS.append(dict(id=tid, area=area, test=desc, result="PASS", evidence=str(ev if ev is not None else ""), seconds=round(time.time() - t0, 1), severity=severity))
        except AssertionError as e:
            RESULTS.append(dict(id=tid, area=area, test=desc, result="FAIL", evidence=str(e)[:500], seconds=round(time.time() - t0, 1), severity=severity))
        except Exception as e:
            RESULTS.append(dict(id=tid, area=area, test=desc, result="FAIL", evidence=f"{type(e).__name__}: {str(e)[:300]}", seconds=round(time.time() - t0, 1), severity=severity, trace=traceback.format_exc()[-700:]))
        print(f"{RESULTS[-1]['result']:5s} {tid:4s} {desc}" + ("" if RESULTS[-1]["result"] == "PASS" else "  <- " + RESULTS[-1]["evidence"][:200]), flush=True)
        return fn
    return deco


class Server:
    """A real uvicorn server on a free port, over a fresh copy of the seeded data."""

    def __init__(self, template: pathlib.Path):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        shutil.copytree(template, self.dir / "data")
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.app = engine_app.create_app(self.dir / "data", SECRET, None, trust_proxy=False)
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
        self.dbpath = self.dir / "data" / "engine.db"

    def conn(self):
        c = db.connect(self.dbpath)
        return c

    def claim_link(self, name: str) -> str:
        c = self.conn()
        pid = c.execute("SELECT id FROM players WHERE name=?", (name,)).fetchone()["id"]
        tok = identity.create_claim(c, SECRET, pid)
        c.close()
        return f"{self.base}/c/{tok}"

    def recovery_code(self, name: str) -> str:
        c = self.conn()
        pid = c.execute("SELECT id FROM players WHERE name=?", (name,)).fetchone()["id"]
        code = identity.create_recovery(c, SECRET, pid, None)["code"]
        c.close()
        return code

    def rows(self, sql, *a):
        c = self.conn()
        try:
            return [dict(r) for r in c.execute(sql, a)]
        finally:
            c.close()

    def stop(self):
        self.srv.should_exit = True
        self.th.join(5)

    def up(self):
        """Start (or restart) the server on the same port with the same database: the phone sees a dead network, not a simulated one."""
        self.srv = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="error", lifespan="off"))
        self.th = threading.Thread(target=self.srv.run, daemon=True)
        self.th.start()
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                return
            except OSError:
                time.sleep(0.05)


class Browser:
    def __init__(self, pw):
        self.b = pw.webkit.launch() if ARGS["engine"] == "webkit" else pw.chromium.launch(executable_path=CHROME, args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"])
        self.errors: list[str] = []

    def page(self, w=390, h=844, sw=False, **kw):
        ctx = self.b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2, is_mobile=True, has_touch=True, service_workers="allow" if sw else "block", **kw)
        p = ctx.new_page()
        p.on("pageerror", lambda e: self.errors.append(str(e)))
        p.on("console", lambda m: self.errors.append("console:" + m.text) if m.type == "error" and "favicon" not in m.text and "Failed to load resource" not in m.text else None)
        return ctx, p


def claim(p, link, expect_name=None):
    p.goto(link)
    p.wait_for_selector("#gYes", timeout=15000)
    if expect_name:
        assert expect_name in p.inner_text("#gTitle"), p.inner_text("#gTitle")
    p.click("#gYes")
    p.wait_for_selector(".codebox", timeout=15000)
    code = p.inner_text(".codebox").replace(" ", "").strip()
    p.click("#gGo")
    p.wait_for_selector("#gAgree", timeout=15000)            # the consent wording comes before anything else
    p.click("#gAgree")
    p.wait_for_function("window.__engine && window.__engine.me() && !document.body.classList.contains('gate') && window.__gonogo.queue()", timeout=15000)
    return code


def wait_q(p, timeout=30000):
    p.wait_for_function("window.__gonogo.state()==='q'", timeout=timeout)


def start_pack(p, title_prefix):
    p.click("#tabs button[data-t=queue]")
    p.wait_for_selector("#packs .card", timeout=10000)
    p.evaluate("(t) => [...document.querySelectorAll('#packs .card')].find(c => c.querySelector('h2').textContent.startsWith(t)).querySelector('button').click()", title_prefix)


def answer_both(p, zone="Strike", pitch_index=0):
    wait_q(p)
    p.click("#bstrike" if zone == "Strike" else "#bball")
    p.wait_for_function("document.getElementById('hlab').textContent.startsWith('Question 2')")
    p.click(f"#opts button:nth-child({pitch_index + 1})")


def finish_pitch(p):
    p.wait_for_function("window.__gonogo.state()==='idle'", timeout=15000)


def local_trials(p):
    return p.evaluate("window.__gonogo.trials()")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["chromium", "webkit"], default="chromium")
    ap.add_argument("--only", default="")
    ap.add_argument("--video", default="/tmp/claude-0/app/content_prep")
    ap.add_argument("--video-keys", default="/tmp/claude-0/app/private_keys_video.json")
    ap.add_argument("--drawn", default="/tmp/claude-0/app/content_sim2")
    ap.add_argument("--drawn-keys", default="/tmp/claude-0/app/work_sim/private_keys.json")
    a = ap.parse_args()
    ARGS.update(engine=a.engine, only=[x for x in a.only.split(",") if x])
    tpl = pathlib.Path(tempfile.mkdtemp()) / "seeded"
    out = seed.seed(tpl, SECRET, pathlib.Path(a.video), pathlib.Path(a.video_keys), "", pathlib.Path(a.drawn), pathlib.Path(a.drawn_keys))
    print("seeded:", out["packs"], "team packs,", out["practice_packs"], "practice packs", flush=True)

    with sync_playwright() as pw:
        B = Browser(pw)

        @check("E1", "Identity", "Claim link: shows the right person, one tap confirms, a pairing code appears, the app opens signed in as him with his playlist; his answers reach the server under his id", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            code = claim(p, S.claim_link("Demo Hitter Four"), "Demo Hitter Four")
            assert len(code) == 8 and code.isdigit()
            assert "Demo Hitter Four" in p.inner_text("#whoTxt") and "Arizona" in p.inner_text("#whoTxt")
            start_pack(p, "Next starter")
            answer_both(p)
            finish_pitch(p)
            p.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=10000)
            rows = S.rows("SELECT a.*, p.name FROM answers a JOIN players p ON p.id=a.player_id")
            ctx.close()
            S.stop()
            assert len(rows) == 2 and {r["name"] for r in rows} == {"Demo Hitter Four"} and {r["task"] for r in rows} == {"zone", "pitch"}, rows
            assert all(r["key"] and r["correct"] in (0, 1) and r["level"] == "MLB" and r["pack_hash"] for r in rows)
            return "2 answers stored under Demo Hitter Four with server keys, level and pack hash"

        @check("E2", "Identity", "The installed-app gap: a fresh app (empty storage) signs in with the pairing code; the browser's credential is retired and signs out cleanly at its next contact", "S1")
        def _():
            S = Server(tpl)
            ctx1, p1 = B.page()
            code = claim(p1, S.claim_link("Demo Hitter Four"))
            ctx2, p2 = B.page()                                     # a different browser context = separate storage, like the Home Screen app
            p2.goto(S.base + "/")
            p2.wait_for_selector("#gPair", timeout=15000)
            p2.fill("#gCode", code[:4] + " " + code[4:])
            p2.click("#gPair")
            p2.wait_for_function("window.__engine && window.__engine.me() && !document.body.classList.contains('gate')", timeout=15000)
            assert "Demo Hitter Four" in p2.inner_text("#whoTxt")
            p1.evaluate("window.__engine.api('/api/me').catch(e => e)")
            p1.wait_for_selector("#gPair", timeout=15000)           # the old credential was retired: the browser is asked who it is
            msg = p1.inner_text("#gBody")
            ctx1.close()
            ctx2.close()
            S.stop()
            assert "signed out" in msg.lower(), msg

        @check("E3", "Identity", "The wrong-person trap: one phone, two hitters. Hitter A's unsent answers are NEVER sent under hitter B's name", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Hitter Four"))
            start_pack(p, "Next starter")
            wait_q(p)
            ctx.set_offline(True)
            answer_both(p)
            finish_pitch(p)
            a_local = [t for t in local_trials(p)]
            assert len(a_local) == 2 and all(not t["synced"] for t in a_local)
            p.once("dialog", lambda d: d.accept())
            p.click("#tabs button[data-t=set]")
            p.click("#notme")
            p.wait_for_selector("#gPair", timeout=10000)
            ctx.set_offline(False)
            link_b = S.claim_link("Demo Switch Hitter")
            p.goto(link_b)
            p.wait_for_selector("#gYes")
            p.click("#gYes")
            p.wait_for_selector(".codebox")
            p.click("#gGo")
            p.wait_for_selector("#gAgree", timeout=15000)
            p.click("#gAgree")
            p.wait_for_function("window.__engine && window.__engine.me() && window.__engine.me().name==='Demo Switch Hitter' && !document.body.classList.contains('gate')", timeout=15000)
            p.evaluate("window.__engine.flush(true)")
            p.wait_for_timeout(1500)
            rows = S.rows("SELECT p.name, COUNT(*) n FROM answers a JOIN players p ON p.id=a.player_id GROUP BY p.name")
            left = local_trials(p)
            ctx.close()
            S.stop()
            assert rows == [], rows
            assert len(left) == 2 and all(t["pid"] == a_local[0]["pid"] and not t["synced"] for t in left), left
            return "A's 2 answers stayed on the phone, unsent, attributed to A; B's flush stored nothing of A's"

        @check("E4", "Sync", "Offline first: answer with no signal, reload still offline (still signed in, playlist cached), come back online: every answer arrives once, banner clears", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page(sw=True)
            claim(p, S.claim_link("Demo Hitter Four"))
            p.evaluate("navigator.serviceWorker.ready.then(() => true)")
            p.reload()
            p.wait_for_function("window.__engine && window.__engine.me() && window.__gonogo.queue()", timeout=15000)
            p.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
            start_pack(p, "Next starter")
            wait_q(p)
            S.stop()                                   # a dead server is what no-signal looks like to the page; WebKit's simulated offline mode cannot reload a service-worker page
            p.click("#bstrike")
            p.wait_for_function("document.getElementById('hlab').textContent.startsWith('Question 2')")
            p.click("#opts button:nth-child(1)")
            finish_pitch(p)
            n_local = len(local_trials(p))
            p.reload()
            p.wait_for_function("window.__engine && window.__engine.me() && window.__gonogo.queue()", timeout=15000)
            assert "Demo Hitter Four" in p.inner_text("#whoTxt") and "2 not sent" in p.inner_text("#pend"), (p.inner_text("#whoTxt"), p.inner_text("#pend"))
            assert p.evaluate("window.__gonogo.queue().packs.length") > 0
            S.up()
            p.evaluate("window.__engine.flush(true)")
            p.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=15000)
            rows = S.rows("SELECT id FROM answers")
            ctx.close()
            S.stop()
            assert n_local == 2 and len(rows) == 2 and len({r["id"] for r in rows}) == 2

        @check("E5", "Sync", "A lost response: the server stores the answers but the reply never reaches the phone; the retry stores nothing twice and the phone ends up with everything marked sent", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Hitter Four"))
            drops = {"n": 0}

            def handler(route):
                if route.request.method == "POST" and drops["n"] < 2:
                    drops["n"] += 1
                    route.fetch()                                    # the server really processes it...
                    route.abort("connectionreset")                  # ...but the phone never hears back
                else:
                    route.continue_()
            p.route("**/api/answers", handler)
            start_pack(p, "Next starter")
            answer_both(p)
            finish_pitch(p)
            p.wait_for_timeout(800)
            first = S.rows("SELECT COUNT(*) n FROM answers")[0]["n"]
            p.evaluate("window.__engine.flush(true)")
            p.wait_for_timeout(500)
            p.evaluate("window.__engine.flush(true)")
            p.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=15000)
            rows = S.rows("SELECT id FROM answers")
            ctx.close()
            S.stop()
            assert len(rows) == 2 and 1 <= first <= 2 and drops["n"] >= 1, (first, len(rows), drops)
            return f"{drops['n']} replies dropped; rows on server 2, none duplicated"

        @check("E6", "Recovery", "Wiped storage: the phone forgets everything; a coach's recovery code signs him back in; answers already sent are on the server and none are doubled", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Hitter Four"))
            start_pack(p, "Next starter")
            answer_both(p)
            finish_pitch(p)
            p.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=10000)
            p.evaluate("new Promise(r => { indexedDB.databases ? indexedDB.databases().then(ds => Promise.all(ds.map(d => indexedDB.deleteDatabase(d.name)))).then(r) : r() })")
            ctx.close()
            ctx2, p2 = B.page()                                       # a brand-new, empty browser stands for wiped storage
            p2.goto(S.base + "/")
            p2.wait_for_selector("#gRecover", timeout=15000)
            p2.fill("#gCode", S.recovery_code("Demo Hitter Four"))
            p2.click("#gRecover")
            p2.wait_for_function("window.__engine && window.__engine.me() && !document.body.classList.contains('gate')", timeout=15000)
            who = p2.inner_text("#whoTxt")
            rows = S.rows("SELECT id FROM answers")
            creds = S.rows("SELECT revoked_reason r FROM credentials ORDER BY id")
            ctx2.close()
            S.stop()
            assert "Demo Hitter Four" in who and len(rows) == 2 and [c["r"] for c in creds] == ["recovery", None], (who, len(rows), creds)

        @check("E7", "Identity", "A revoked credential: the next contact signs the phone out with a clear message and the unsent answers stay on the phone", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Hitter Four"))
            start_pack(p, "Next starter")
            wait_q(p)
            ctx.set_offline(True)
            answer_both(p)
            finish_pitch(p)
            c = S.conn()
            identity.revoke_credential(c, c.execute("SELECT id FROM credentials").fetchone()["id"], None)
            c.close()
            ctx.set_offline(False)
            p.evaluate("window.__engine.flush(true)")
            p.wait_for_selector("#gPair", timeout=15000)
            msg = p.inner_text("#gBody")
            local = p.evaluate("(async () => (await window.__gonogo.trials()).length)()")
            stored = S.rows("SELECT COUNT(*) n FROM answers")[0]["n"]
            ctx.close()
            S.stop()
            assert "signed out" in msg.lower() and local == 2 and stored == 0, (msg, local, stored)

        @check("E8", "Surfacing", "Coach settings reach the phone and cannot be changed on it: Visalia gets 200 ms and the low-behind-home view; drawn pitches log that camera; a practice note says these are not his opponent", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Hitter One"), "Demo Hitter One")
            assert p.input_value("#off") == "0.200" and p.input_value("#view") == "low_home"
            assert "practice" in (p.inner_text("#now") + p.evaluate("(window.__engine.playlist().notes||[]).join(' ')")).lower()
            start_pack(p, "Next starter")
            answer_both(p)
            finish_pitch(p)
            p.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=10000)
            rows = S.rows("SELECT camera, pause_ms, view FROM answers")
            ctx.close()
            S.stop()
            assert rows and all(r["camera"].startswith("sim") and r["pause_ms"] == 200 for r in rows), rows

        @check("E9", "Surfacing", "Server-side truth: a phone that lies about the score, the key or the pack it was shown cannot change what is stored", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Hitter Four"))
            pl = p.evaluate("window.__engine.playlist()")
            pack = pl["packs"][0]
            item = pack["items"][0]["id"]
            body = {"answers": [dict(id="lie-0000-0001", pack=pack["id"], clip=item, task="zone", mode=pack["mode"], call="Strike", correct=1, key="Strike", rt_ms=300, ts="2026-10-10T00:00:00Z", app="engine-1"),
                                dict(id="lie-0000-0002", pack="0" * 64, clip=item, task="zone", mode="train", call="Strike", correct=1),
                                dict(id="lie-0000-0003", pack=pack["id"], clip="not-an-item", task="zone", mode=pack["mode"], call="Strike", correct=1)]}
            r = p.evaluate("(b) => window.__engine.api('/api/answers', {body: b})", body)
            rows = S.rows("SELECT id, key, correct, client_correct FROM answers")
            ctx.close()
            S.stop()
            assert r["stored"] == ["lie-0000-0001"] and len(r["rejected"]) == 2, r
            truth = [it for it in pack["items"] if it["id"] == item][0]["keys"]["strike"]
            assert rows[0]["key"] == ("Strike" if truth else "Ball") and rows[0]["correct"] == int(truth) and rows[0]["client_correct"] == 1

        @check("E10", "Surfacing", "Assessment: no answers on the phone, scored by the server, offered once", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Hitter Four"))
            titles = p.evaluate("window.__gonogo.queue().packs.map(p => [p.title, p.mode])")
            assert ["Assessment", "assess"] in titles, titles
            start_pack(p, "Assessment")
            answer_both(p)
            p.wait_for_function("document.getElementById('hlab').textContent==='Recorded'", timeout=15000)
            assert "Right answer" not in p.inner_text("#res")
            p.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=10000)
            rows = S.rows("SELECT mode, key, correct FROM answers")
            p.evaluate("window.__engine.api('/api/playlist').then(r => window.__pl = r)")
            p.wait_for_function("window.__pl")
            asm = p.evaluate("window.__pl.packs.filter(p => p.mode === 'assess').map(p => [!!p.resume, p.items.length])")
            ctx.close()
            S.stop()
            assert rows and all(r["mode"] == "assess" and r["key"] and r["correct"] in (0, 1) for r in rows), rows
            assert asm == [[True, 5]], asm                          # one item of six answered: the form resumes with the five left, it is not "taken"
            return "scored on the server; a started form resumes with the 5 items left"

        @check("E11", "Surfacing", "Switch hitter: side selector shown, both sides' packs exist, choosing a side filters the queue", "S2")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            claim(p, S.claim_link("Demo Switch Hitter"))
            assert p.is_visible("#sideSel")
            p.select_option("#sideSel", "L")
            left = p.evaluate("window.__gonogo.queue().packs.map(p => p.side)")
            p.select_option("#sideSel", "R")
            right = p.evaluate("window.__gonogo.queue().packs.map(p => p.side)")
            ctx.close()
            S.stop()
            assert left and set(left) == {"L"} and right and set(right) == {"R"}, (left, right)

        @check("E12", "Identity", "A claim link works once; a used, wrong or expired link looks the same and says so plainly", "S1")
        def _():
            S = Server(tpl)
            link = S.claim_link("Demo Hitter Four")
            ctx, p = B.page()
            claim(p, link)
            ctx.close()
            ctx2, p2 = B.page()
            p2.goto(link)
            p2.wait_for_function("document.getElementById('gTitle').textContent==='Link problem'", timeout=15000)
            m1 = p2.inner_text("#gBody")
            p2.goto(S.base + "/c/definitely-not-a-real-token")
            p2.wait_for_function("document.getElementById('gTitle').textContent==='Link problem'", timeout=15000)
            m2 = p2.inner_text("#gBody")
            ctx2.close()
            S.stop()
            assert m1 == m2 and "ask a coach" in m1.lower(), (m1, m2)

        @check("E13", "Identity", "Wrong codes show the server's message and the throttle stops guessing", "S2")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            p.goto(S.base + "/")
            p.wait_for_selector("#gPair")
            p.fill("#gCode", "00000000")
            p.click("#gPair")
            p.wait_for_function("document.getElementById('gMsg').textContent.length > 12 && !document.getElementById('gMsg').textContent.startsWith('Checking')", timeout=10000)
            first = p.inner_text("#gMsg")
            res = p.evaluate("""async () => { let last = 0; for (let i = 0; i < 40; i++) { const r = await fetch('/api/pair', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code: String(10000000 + i)})}); last = r.status; if (last === 429) return i } return last }""")
            ctx.close()
            S.stop()
            assert "not valid" in first.lower() and isinstance(res, int) and res < 40, (first, res)
            return f"throttled after {res} more guesses"

        for w, h in ((320, 568), (390, 844), (820, 1180)):
            @check(f"E14-{w}", "Layout", f"{w}x{h}: gate screens and the signed-in app have no sideways scroll, buttons are at least 44 px, and the Strike/Ball buttons are on screen", "S2")
            def _(w=w, h=h):
                S = Server(tpl)
                ctx, p = B.page(w, h)
                p.goto(S.base + "/")
                p.wait_for_selector("#gPair")
                over1 = p.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                small1 = p.evaluate("[...document.querySelectorAll('#gate button')].filter(b => b.getBoundingClientRect().height < 44).map(b => b.id)")
                claim(p, S.claim_link("Demo Hitter Four"))
                start_pack(p, "Next starter")
                wait_q(p)
                box = p.evaluate("(() => { const r = document.getElementById('bstrike').getBoundingClientRect(); return [r.bottom, innerHeight, document.documentElement.scrollWidth - document.documentElement.clientWidth] })()")
                ctx.close()
                S.stop()
                assert over1 <= 1 and not small1 and box[2] <= 1 and box[0] <= box[1] + 1, (over1, small1, box)

        @check("E16", "Consent", "Consent comes first: after the claim the hitter sees the wording and nothing else; no answer reaches the server before he agrees; after he agrees the app opens and his agreement is on record", "S1")
        def _():
            S = Server(tpl)
            ctx, p = B.page()
            p.goto(S.claim_link("Demo Hitter Four"))
            p.wait_for_selector("#gYes", timeout=15000)
            p.click("#gYes")
            p.wait_for_selector(".codebox", timeout=15000)
            p.click("#gGo")
            p.wait_for_selector("#gAgree", timeout=15000)
            body = p.inner_text("#gBody")
            assert "answers" in body.lower() and p.evaluate("document.body.classList.contains('gate')")
            assert S.rows("SELECT COUNT(*) n FROM consents")[0]["n"] == 0 and S.rows("SELECT COUNT(*) n FROM answers")[0]["n"] == 0
            p.click("#gAgree")
            p.wait_for_function("window.__engine && window.__engine.me() && !document.body.classList.contains('gate')", timeout=15000)
            rows = S.rows("SELECT version FROM consents")
            ctx.close()
            S.stop()
            assert len(rows) == 1 and rows[0]["version"]
            return f"gate shown, agreement recorded for version {rows[0]['version']}"

        @check("E17", "Shared iPad", "Shared iPad: a hitter's phone issues a code, he signs in on the iPad, answers land under his name, Done signs him out, and his phone stayed signed in throughout", "S1")
        def _():
            S = Server(tpl)
            ctxp, ph = B.page()
            claim(ph, S.claim_link("Demo Hitter Four"))
            ph.click("#guestShow") if ph.is_visible("#guestShow") else ph.evaluate("document.getElementById('guestShow').click()")
            ph.wait_for_function("/\\d{4} \\d{4}/.test(document.getElementById('pairOut').textContent)", timeout=10000)
            code = re.search(r"(\d{4} \d{4})", ph.inner_text("#pairOut")).group(1)
            ctxi, ip = B.page()
            ip.goto(S.base + "/")
            ip.wait_for_selector("#gPair", timeout=15000)
            ip.fill("#gCode", code)
            ip.click("#gPair")
            ip.wait_for_function("window.__engine && window.__engine.me() && window.__engine.me().name==='Demo Hitter Four' && !document.body.classList.contains('gate') && window.__gonogo.queue()", timeout=15000)
            assert ip.inner_text("#notme") == "Done"
            start_pack(ip, "Next starter")
            wait_q(ip)
            ip.click("#bstrike")
            ip.wait_for_function("document.getElementById('hlab').textContent.startsWith('Question 2')")
            ip.click("#opts button:nth-child(1)")
            finish_pitch(ip)
            ip.evaluate("window.__engine.flush(true)")
            ip.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=15000)
            ip.click("#notme")                                   # Done: nothing unsent, so no question asked
            ip.wait_for_selector("#gPair", timeout=10000)
            assert "Demo Hitter Four" not in ip.inner_text("body")
            n = S.rows("SELECT COUNT(*) n FROM answers a JOIN players p ON p.id=a.player_id WHERE p.name='Demo Hitter Four'")[0]["n"]
            shared = S.rows("SELECT shared, revoked_reason FROM credentials WHERE shared=1")
            phone_ok = ph.evaluate("window.__engine.api('/api/me').then(m => m.player.name)")
            ctxi.close(); ctxp.close()
            S.stop()
            assert n == 2 and len(shared) == 1 and shared[0]["revoked_reason"] == "signed_out" and phone_ok == "Demo Hitter Four", (n, shared, phone_ok)
            return "2 answers under his name from the iPad; iPad credential retired on Done; phone still signed in"

        @check("E18", "Shared iPad", "Shared iPad left alone: after the idle time it flushes, signs the hitter out and shows the welcome screen", "S1")
        def _():
            S = Server(tpl)
            ctxp, ph = B.page()
            claim(ph, S.claim_link("Demo Hitter Four"))
            ph.evaluate("document.getElementById('guestShow').click()")
            ph.wait_for_function("/\\d{4} \\d{4}/.test(document.getElementById('pairOut').textContent)", timeout=10000)
            code = re.search(r"(\d{4} \d{4})", ph.inner_text("#pairOut")).group(1)
            ctxi, ip = B.page()
            ip.add_init_script("window.__IDLE_MS_FOR_TEST = 1500")
            ip.goto(S.base + "/")
            ip.wait_for_selector("#gPair", timeout=15000)
            ip.fill("#gCode", code)
            ip.click("#gPair")
            ip.wait_for_function("window.__engine && window.__engine.me() && !document.body.classList.contains('gate')", timeout=15000)
            ip.wait_for_selector("#gPair", timeout=20000)         # nobody touches it: it signs out by itself
            live = S.rows("SELECT COUNT(*) n FROM credentials WHERE shared=1 AND revoked_at IS NULL")[0]["n"]
            ctxi.close(); ctxp.close()
            S.stop()
            assert live == 0, live
            return "signed out on its own; server credential retired"

        @check("E15", "Console", "No uncaught script errors or console errors across the whole run", "S1")
        def _():
            assert not B.errors, B.errors[:3]

        B.b.close()
    n = len(RESULTS)
    ok = sum(r["result"] == "PASS" for r in RESULTS)
    pathlib.Path(__file__).with_name(f"results_engine_{a.engine}.json").write_text(json.dumps(RESULTS, indent=1))
    print(f"\n{n} checks, {ok} pass, {n - ok} fail")
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
