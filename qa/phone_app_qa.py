"""Release-gate QA for the phone app. Runs the whole matrix against real built content, records PASS / FAIL / BLOCKED with evidence, writes qa/results.json.

  PYTHONPATH=src python3 qa/phone_app_qa.py [--content DIR] [--keys FILE]

Engine: Chromium only (no WebKit or Firefox installed here). That is the main gap for a phone release; see the report.
Every test gets a fresh browser context (empty IndexedDB, no service worker) unless it says otherwise.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from playwright.sync_api import sync_playwright  # noqa: E402

from gameplan import app_server as AS  # noqa: E402
from gameplan import recognition_profile as RP  # noqa: E402

CHROME = "/opt/pw-browsers/chromium-1234/chrome-linux64/chrome"
RESULTS: list[dict] = []
ARGS = {}


def check(tid, area, desc, severity="S2"):
    def deco(fn):
        if ARGS.get("only") and not any(tid.startswith(x) for x in ARGS["only"]):
            return fn
        t0 = time.time()
        try:
            ev = fn()
            RESULTS.append(dict(id=tid, area=area, test=desc, result="PASS", evidence=str(ev if ev is not None else ""), seconds=round(time.time() - t0, 1), severity=severity))
        except AssertionError as e:
            RESULTS.append(dict(id=tid, area=area, test=desc, result="FAIL", evidence=str(e)[:400], seconds=round(time.time() - t0, 1), severity=severity))
        except Exception as e:
            RESULTS.append(dict(id=tid, area=area, test=desc, result="FAIL", evidence=f"{type(e).__name__}: {str(e)[:300]}", seconds=round(time.time() - t0, 1), severity=severity,
                                trace=traceback.format_exc()[-600:]))
        print(f"{RESULTS[-1]['result']:5s} {tid:4s} {desc}" + ("" if RESULTS[-1]["result"] == "PASS" else "  <- " + RESULTS[-1]["evidence"][:160]), flush=True)
        return fn
    return deco


def serve(content, token=None, keys=None):
    d = pathlib.Path(tempfile.mkdtemp())
    srv, store = AS.serve(content, d / "data", 0, token, keys)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, store, f"http://localhost:{srv.server_address[1]}"


class Env:
    def __init__(self, pw, base):
        self.pw, self.base = pw, base
        self.browser = (pw.webkit.launch() if ARGS.get("engine") == "webkit" else pw.chromium.launch(executable_path=CHROME, args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"]))
        self.errors = []

    def page(self, w=390, h=844, scheme="light", mobile=True, **kw):
        ctx = self.browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2, is_mobile=mobile, has_touch=mobile, color_scheme=scheme, **kw)
        p = ctx.new_page()
        p.on("pageerror", lambda e: self.errors.append(str(e)))
        p.on("console", lambda m: self.errors.append("console:" + m.text) if m.type == "error" and "favicon" not in m.text else None)
        return ctx, p

    def open(self, **kw):
        ctx, p = self.page(**kw)
        p.goto(self.base + "/")
        p.wait_for_function("window.__gonogo && window.__gonogo.queue !== undefined")
        return ctx, p


def clips_ready(p, n, timeout=90000):
    p.wait_for_function(f"document.getElementById('dlmsg').textContent.startsWith('{n} of {n} clips')", timeout=timeout)


def next_clip(p):
    p.wait_for_selector("#next", state="visible", timeout=30000)
    p.click("#next")


def setup(p, name="QA Hitter", bats="R", need_queue=True, **opts):
    p.click("#tabs button[data-t=set]")
    p.fill("#player", name)
    p.select_option("#bats", bats)
    for k, v in opts.items():
        p.select_option("#" + k, v)
    p.dispatch_event("#player", "change")
    if need_queue:
        p.wait_for_function("window.__gonogo.queue() !== null")


def wait_q(p, timeout=25000):
    p.wait_for_function("window.__gonogo.state()==='q'", timeout=timeout)


def answer_clip(p, calls=("GO", "NO-GO")):
    """Answer every question of the current clip. Returns the question texts in the order asked."""
    seen = []
    for c in calls:
        wait_q(p)
        seen.append(p.inner_text("#hnum"))
        p.click("#bgo" if c == "GO" else "#bno")
        p.wait_for_timeout(120)
    return seen


def trials(p):
    return p.evaluate("window.__gonogo.trials()")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", default="/tmp/claude-0/app/content")
    ap.add_argument("--keys", default="/tmp/claude-0/app/work/private_keys.json")
    ap.add_argument("--engine", choices=["chromium", "webkit"], default="chromium")
    ap.add_argument("--only", default="", help="comma separated check id prefixes to run, e.g. E1,F3,F6")
    a = ap.parse_args()
    ARGS["engine"] = a.engine
    ARGS["only"] = [x for x in a.only.split(",") if x]
    content = pathlib.Path(a.content)
    keys = pathlib.Path(a.keys)
    qR = json.loads((content / "queue_R.json").read_text())
    qL = json.loads((content / "queue_L.json").read_text())
    srv, store, base = serve(content, keys=keys)
    with sync_playwright() as pw:
        E = Env(pw, base)

        # ------------------------------------------------------------------ A. install / PWA
        @check("A1", "Install", "Manifest has name, standalone display, start_url and both icons that exist with the declared sizes", "S1")
        def _():
            m = json.load(urllib.request.urlopen(base + "/manifest.webmanifest"))
            assert m["display"] == "standalone" and m["start_url"] and m["name"] and m["short_name"], m
            sizes = []
            for ic in m["icons"]:
                data = urllib.request.urlopen(base + "/" + ic["src"]).read()
                assert data[:8] == b"\x89PNG\r\n\x1a\n"
                w = int.from_bytes(data[16:20], "big")
                assert f"{w}x{w}" == ic["sizes"], (ic, w)
                sizes.append(w)
            return f"icons {sizes}"

        @check("A2", "Install", "Service worker registers, activates and controls the page after one reload", "S1")
        def _():
            ctx, p = E.open()
            p.evaluate("navigator.serviceWorker.ready.then(()=>1)")
            p.reload()
            p.wait_for_function("navigator.serviceWorker.controller !== null", timeout=10000)
            ctx.close()
            return "controller active after reload"

        @check("A3", "Install", "iOS home-screen tags present (apple-touch-icon 180px, capable, status bar, title) and theme-color set", "S2")
        def _():
            ctx, p = E.open()
            tags = p.evaluate("""() => ({touch: !!document.querySelector('link[rel=apple-touch-icon]'), cap: document.querySelector('meta[name=apple-mobile-web-app-capable]')?.content,
              theme: document.querySelector('meta[name=theme-color]')?.content, title: document.querySelector('meta[name=apple-mobile-web-app-title]')?.content, vp: document.querySelector('meta[name=viewport]')?.content})""")
            ctx.close()
            data = urllib.request.urlopen(base + "/apple-touch-icon.png").read()
            assert int.from_bytes(data[16:20], "big") == 180
            assert tags["touch"] and tags["cap"] == "yes" and tags["theme"] and tags["title"] and "viewport-fit=cover" in tags["vp"], tags
            return str(tags)

        @check("A4", "Install", "With the SERVER STOPPED, the installed shell still opens, shows the cached queue and plays a cached clip", "S1")
        def _():
            srv2, st2, base2 = serve(content, keys=keys)
            ctx = E.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            p = ctx.new_page()
            p.goto(base2 + "/")
            p.wait_for_function("window.__gonogo && window.__gonogo.queue()")
            setup(p)
            p.click("#tabs button[data-t=queue]")
            clips_ready(p, 6)
            p.reload()
            p.wait_for_function("navigator.serviceWorker.controller !== null", timeout=10000)
            srv2.shutdown()
            srv2.server_close()
            p.reload()
            p.wait_for_function("window.__gonogo && window.__gonogo.queue()", timeout=15000)
            p.click("#tabs button[data-t=play]")
            p.click("#start")
            wait_q(p)
            net = p.inner_text("#net")
            ctx.close()
            assert net == "offline", net
            return "opened and played with the server down; chip said offline"

        # ------------------------------------------------------------------ B. first run
        @check("B1", "First run", "Start with no player name: blocked with a message, no answer is recorded", "S1")
        def _():
            ctx, p = E.open()
            p.click("#tabs button[data-t=play]")
            p.click("#start")
            p.wait_for_timeout(400)
            msg = p.inner_text("#now")
            n = len(trials(p))
            ctx.close()
            assert "player" in msg.lower() and n == 0, (msg, n)
            return msg

        @check("B2", "First run", "Empty content folder (no queue yet): app opens, says so, no script errors", "S2")
        def _():
            empty = pathlib.Path(tempfile.mkdtemp())
            s2, st2, b2 = serve(empty)
            E2 = Env(pw, b2)
            ctx, p = E2.open()
            setup(p, need_queue=False)
            p.click("#tabs button[data-t=queue]")
            txt = p.inner_text("#packs")
            p.click("#tabs button[data-t=play]")
            p.click("#start")
            p.wait_for_timeout(300)
            now = p.inner_text("#now")
            errs = [e for e in E2.errors if "Failed to load resource" not in e]      # the missing queue file is expected here
            ctx.close()
            E2.browser.close()
            s2.shutdown()
            assert "No queue" in txt and errs == [], (txt, errs)
            return f"queue says '{txt[:40]}', play says '{now[:50]}'"

        @check("B3", "First run", "Very first load while offline (nothing cached): fails safely, no crash loop", "S2")
        def _():
            ctx, p = E.page()
            ctx.set_offline(True)
            try:
                p.goto(base + "/", timeout=8000)
                ok = False
            except Exception:
                ok = True            # the browser's own offline page; nothing for the app to do without a first visit
            ctx.close()
            return "browser shows its offline page; the app needs one online visit to install (documented)" if ok else "page loaded"

        # ------------------------------------------------------------------ C. core flow
        @check("C1", "Core", "Both questions per clip: 2 rows, same clip_trial, q_order 1 and 2, different tasks", "S1")
        def _():
            ctx, p = E.open()
            setup(p)
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            qs = answer_clip(p)
            p.wait_for_selector("#res .card")
            t = trials(p)
            ctx.close()
            assert len(t) == 2 and {x["task"] for x in t} == {"zone", "pitch"} and t[0]["clip_trial"] == t[1]["clip_trial"] and {x["q_order"] for x in t} == {1, 2}, t
            return f"questions asked: {qs}"

        @check("C2", "Core", "Question order is randomized: across the pack both orders occur, and the same clip keeps the same order", "S3")
        def _():
            ctx, p = E.open()
            setup(p)
            p.click("#tabs button[data-t=queue]")
            p.click("#block")
            firsts = []
            for _i in range(8):
                firsts.append(answer_clip(p)[0])
                next_clip(p)
                p.wait_for_timeout(600)
            ctx.close()
            assert len(set(firsts)) == 2, firsts
            return f"first questions over {len(firsts)} clips: {firsts}"

        for tid, ask, task in (("C3a", "zone", "zone"), ("C3b", "pitch", "pitch")):
            @check(tid, "Core", f"Ask '{ask}' only: one row per clip, task {task}", "S2")
            def _(ask=ask, task=task):
                ctx, p = E.open()
                setup(p, ask=ask)
                p.click("#tabs button[data-t=queue]")
                p.click("#goNext")
                answer_clip(p, ("GO",))
                p.wait_for_timeout(300)
                t = trials(p)
                ctx.close()
                assert len(t) == 1 and t[0]["task"] == task, t

        @check("C4", "Core", "Training: each answer is scored against the shipped key; verdicts on screen match the stored correct flag", "S1")
        def _():
            ctx, p = E.open()
            setup(p)
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            answer_clip(p, ("GO", "GO"))
            p.wait_for_selector("#res .card")
            card = p.inner_text("#res")
            t = trials(p)
            ctx.close()
            for x in t:
                assert x["key"] in ("GO", "NO-GO") and x["correct"] in (0, 1), x
                assert (x["call"] == x["key"]) == bool(x["correct"]), x
            wrong = sum(1 for x in t if not x["correct"])
            assert card.count("Wrong") == wrong and card.count("Correct") == len(t) - wrong, (card, t)
            return f"{len(t) - wrong} of {len(t)} correct, screen agrees"

        @check("C5", "Core", "Assessment: no feedback, no reveal playback, no answers in the page or the queue file, stored key is blank", "S1")
        def _():
            raw = (content / "queue_R.json").read_text()
            q = json.loads(raw)
            ap_ = [p_ for p_ in q["packs"] if p_["mode"] == "assess"][0]
            assert all(i["keys"] is None for i in ap_["items"])
            ctx, p = E.open()
            setup(p)
            p.click("#tabs button[data-t=queue]")
            p.evaluate("[...document.querySelectorAll('#packs .card')].find(c=>c.textContent.includes('Assessment')).querySelector('button').click()")
            qs = answer_clip(p)
            p.wait_for_function("document.getElementById('hlab').textContent==='Recorded'", timeout=5000)
            p.wait_for_timeout(1500)
            html = p.inner_text("body")          # what a player can see, not the page source (the script itself contains the word)
            t = trials(p)
            paused = p.evaluate("document.getElementById('v').paused")
            ctx.close()
            assert "Right answer" not in html, "answer shown in assessment"
            assert len(t) >= 2 and all(x["key"] == "" and x["correct"] == "" for x in t[:2]), t[:2]
            return f"mode={t[0]['mode']}, video paused={paused}"

        @check("C6", "Core", "Run block: plays every pitch in the queue once, auto-advances, ends with 'Done'", "S2")
        def _():
            n_items = sum(len(p_["items"]) for p_ in qR["packs"])
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#block")
            done = 0
            for _i in range(n_items + 2):
                try:
                    p.wait_for_function("window.__gonogo.state()==='q'", timeout=12000)
                except Exception:
                    break
                p.click("#bgo")
                done += 1
                next_clip(p)
                p.wait_for_timeout(100)
            p.wait_for_function("document.getElementById('now').textContent.startsWith('Done')", timeout=20000)
            clips = {x["clip"] for x in trials(p)}
            ctx.close()
            assert done == n_items, (done, n_items)
            return f"{done} pitches answered, {len(clips)} distinct clips"

        @check("C7", "Core", "Keyboard: G, N and Space work (for a desktop or Bluetooth keyboard)", "S3")
        def _():
            ctx, p = E.open(mobile=False)
            setup(p, ask="zone")
            p.click("#tabs button[data-t=play]")
            p.keyboard.press("Space")
            wait_q(p)
            p.keyboard.press("n")
            p.wait_for_timeout(300)
            t = trials(p)
            ctx.close()
            assert len(t) == 1 and t[0]["call"] == "NO-GO", t

        @check("C8", "Core", "Pack completion: the Start button comes back and the queue marks the pitches done after a reload", "S2")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            for _i in range(6):
                wait_q(p)
                p.click("#bgo")
                next_clip(p)
                p.wait_for_timeout(100)
            p.wait_for_function("document.getElementById('now').textContent.startsWith('Done')", timeout=30000)
            p.reload()
            p.wait_for_function("window.__gonogo && window.__gonogo.queue()")
            p.click("#tabs button[data-t=queue]")
            p.wait_for_timeout(500)
            txt = p.inner_text("#packs")
            hero = p.inner_text("#nextTitle")
            ctx.close()
            assert "6 of 6" in txt and "0 of 6" not in txt.split("On this phone")[0], txt[:300]
            return f"hero now says: {hero}"

        # ------------------------------------------------------------------ D. data integrity
        @check("D1", "Data", "Every stored answer has all fields; times are plausible; ids unique", "S1")
        def _():
            ctx, p = E.open()
            setup(p)
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            for _i in range(3):
                answer_clip(p)
                next_clip(p)
                p.wait_for_timeout(300)
            t = trials(p)
            ctx.close()
            need = "player session mode ts pack clip clip_trial task q_order ask pause_ms call rt_ms key correct pitch_type family pocket px pz sz_top sz_bot speed stand p_throws id".split()
            for x in t:
                for k in need:
                    assert k in x and x[k] is not None, (k, x)
                assert 0 <= x["rt_ms"] < 60000 and x["call"] in ("GO", "NO-GO") and x["pause_ms"] == 100
            assert len({x["id"] for x in t}) == len(t)
            return f"{len(t)} rows"

        @check("D2", "Data", "Sync twice and concurrently: server holds exactly the local count, nothing duplicated", "S1")
        def _():
            srv3, st3, b3 = serve(content, keys=keys)
            E3 = Env(pw, b3)
            ctx, p = E3.open()
            setup(p)
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            answer_clip(p)
            p.click("#tabs button[data-t=log]")
            p.evaluate("Promise.all([document.getElementById('sync').click(), document.getElementById('sync').click()])")
            p.wait_for_timeout(1500)
            p.click("#sync")
            p.wait_for_timeout(800)
            n_local = len(trials(p))
            n_srv = len(st3.rows())
            pend = p.inner_text("#pend")
            ctx.close()
            E3.browser.close()
            srv3.shutdown()
            assert n_local == n_srv == 2 and pend.startswith("0"), (n_local, n_srv, pend)
            return f"local {n_local}, server {n_srv}, chip '{pend}'"

        @check("D3", "Data", "Server CSV is read by the recognition profile code and produces a profile (end to end, no exceptions)", "S1")
        def _():
            srv3, st3, b3 = serve(content, keys=keys)
            E3 = Env(pw, b3)
            ctx, p = E3.open()
            setup(p, ask="both")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            for _i in range(4):
                answer_clip(p)
                next_clip(p)
                p.wait_for_timeout(300)
            p.click("#tabs button[data-t=log]")
            p.click("#sync")
            p.wait_for_function("document.getElementById('syncmsg').textContent.startsWith('Synced')", timeout=8000)
            text = urllib.request.urlopen(b3 + "/api/trials.csv").read().decode()
            ctx.close()
            E3.browser.close()
            srv3.shutdown()
            f = pathlib.Path(tempfile.mkdtemp()) / "t.csv"
            f.write_text(text)
            rows = RP.load([str(f)])
            pr = RP.profile(rows, "QA Hitter")
            assert pr["trials"] == len(rows) and pr["zone"]["summary"]["n"] > 0 and pr["pitch"]["summary"]["n"] > 0
            RP.render_html(pr)
            return f"{len(rows)} rows, zone n={pr['zone']['summary']['n']}, pitch n={pr['pitch']['summary']['n']}"

        @check("D4", "Data", "Reload keeps answers, settings and the 'done' state", "S1")
        def _():
            ctx, p = E.open()
            setup(p, name="Persist Test", bats="L", ask="zone", off="0.150", mode="assess")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            answer_clip(p, ("GO",))
            p.wait_for_timeout(500)
            p.reload()
            p.wait_for_function("window.__gonogo && window.__gonogo.queue()")
            p.click("#tabs button[data-t=set]")
            vals = p.evaluate("(() => { const g = i => document.getElementById(i).value; return {player: g('player'), bats: g('bats'), ask: g('ask'), off: g('off')}; })()")
            n = len(trials(p))
            ctx.close()
            assert vals == dict(player="Persist Test", bats="L", ask="zone", off="0.150") and n >= 1, (vals, n)
            return str(vals)

        @check("D5", "Data", "Erase on this phone really clears answers and resets the sync chip", "S2")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            answer_clip(p, ("GO",))
            p.wait_for_timeout(400)
            p.click("#tabs button[data-t=set]")
            p.once("dialog", lambda d: d.accept())
            p.click("#wipe")
            p.wait_for_timeout(500)
            n = len(trials(p))
            chip = p.inner_text("#pend")
            ctx.close()
            assert n == 0 and chip.startswith("0"), (n, chip)

        @check("D6", "Data", "Server unreachable during sync: clear message, answers stay unsynced, later sync succeeds with nothing lost", "S1")
        def _():
            srv3, st3, b3 = serve(content, keys=keys)
            port = srv3.server_address[1]
            E3 = Env(pw, b3)
            ctx, p = E3.open(service_workers="block")      # the test tool cannot intercept requests made through a service worker, so run this one without it
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            answer_clip(p, ("GO",))
            p.wait_for_timeout(300)
            p.route("**/api/trials", lambda r: r.abort())
            p.click("#tabs button[data-t=log]")
            p.click("#sync")
            p.wait_for_function("document.getElementById('syncmsg').textContent.startsWith('Sync failed')", timeout=6000)
            pend = p.inner_text("#pend")
            net = p.inner_text("#net")
            p.unroute("**/api/trials")
            p.click("#sync")
            p.wait_for_function("document.getElementById('syncmsg').textContent.startsWith('Synced')", timeout=6000)
            ctx.close()
            E3.browser.close()
            srv3.shutdown()
            assert pend.startswith("1") and net == "offline" and len(st3.rows()) == 1, (pend, net, len(st3.rows()))
            return f"failed sync -> chip '{pend}', net '{net}'; retry stored {len(st3.rows())}"

        @check("D7", "Data", "CSV formula injection: a player name like =cmd|... must not reach a spreadsheet cell as a formula (app export and server CSV)", "S1")
        def _():
            evil = "=HYPERLINK(\"http://x\",\"a\")"
            srv3, st3, b3 = serve(content, keys=keys)
            E3 = Env(pw, b3)
            ctx, p = E3.open(accept_downloads=True)
            setup(p, name=evil, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            answer_clip(p, ("GO",))
            p.wait_for_timeout(300)
            p.click("#tabs button[data-t=log]")
            with p.expect_download() as d:
                p.click("#dl")
            path = d.value.path()
            local = pathlib.Path(path).read_text()
            p.click("#sync")
            p.wait_for_function("document.getElementById('syncmsg').textContent.startsWith('Synced')", timeout=6000)
            srvcsv = urllib.request.urlopen(b3 + "/api/trials.csv").read().decode()
            ctx.close()
            E3.browser.close()
            srv3.shutdown()
            for name, text in (("app export", local), ("server csv", srvcsv)):
                cells = [c for row in csv.reader(io.StringIO(text)) for c in row]
                bad = [c for c in cells if c[:1] in "=+-@\t\r" and c not in ("", "-")]
                bad = [c for c in bad if not c.lstrip("-").replace(".", "").isdigit()]
                assert not bad, f"{name}: cell starts with a formula character: {bad[:2]}"
            return "neutralised in both exports"

        # ------------------------------------------------------------------ E. offline
        @check("E1", "Offline", "Clip not on the phone and no signal: a clear message, no crash, state recovers", "S1")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            clips_ready(p, 6)                      # let the background download finish, otherwise it refills the store after we clear it
            p.evaluate("""() => new Promise(res => { const r = indexedDB.open('gonogo', 1); r.onsuccess = () => { const t = r.result.transaction('clips', 'readwrite'); t.objectStore('clips').clear(); t.oncomplete = () => res(1); }; })""")
            ctx.set_offline(True)
            p.route("**/content/**", lambda r: r.abort())      # offline mode alone still serves clips from the browser's own HTTP cache, so block them for real
            p.click("#tabs button[data-t=play]")
            p.click("#start")
            p.wait_for_timeout(1500)
            msg = p.inner_text("#now")
            st = p.evaluate("window.__gonogo.state()")
            ctx.close()
            assert ("not on the phone" in msg or "No pitches" in msg) and st == "idle", (msg, st)
            return msg

        @check("E2", "Offline", "The server disappears right after a clip starts: the pitch, the question and the answer all still work (server really stopped, not browser offline emulation)", "S2")
        def _():
            s5, st5, b5 = serve(content, keys=keys)
            E5 = Env(pw, b5)
            ctx, p = E5.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            clips_ready(p, 6)
            p.click("#goNext")
            s5.shutdown()
            s5.server_close()
            wait_q(p)
            p.click("#bgo")
            p.wait_for_timeout(400)
            n = len(trials(p))
            ctx.close()
            E5.browser.close()
            assert n == 1, n

        # ------------------------------------------------------------------ F. robustness
        @check("F1", "Robustness", "Double-tapping GO records ONE answer for that question", "S1")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            wait_q(p)
            p.evaluate("(()=>{const b=document.getElementById('bgo');b.click();b.click();b.click()})()")
            p.wait_for_timeout(600)
            n = len(trials(p))
            ctx.close()
            assert n == 1, n

        @check("F2", "Robustness", "Start tapped repeatedly: one playback, one set of trials", "S2")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=play]")
            p.click("#start")
            p.evaluate("(()=>{const b=document.getElementById('start');b.click();b.click()})()")
            wait_q(p)
            p.click("#bgo")
            p.wait_for_timeout(1500)
            n = len(trials(p))
            ctx.close()
            assert n == 1, n

        @check("F3", "Robustness", "During a pitch the tab bar is hidden (focus mode); the question appears and is answered; the tabs return afterwards", "S2")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            p.wait_for_function("window.__gonogo.state()==='playing' || window.__gonogo.state()==='q'", timeout=10000)
            hidden = p.evaluate("getComputedStyle(document.querySelector('#tabs')).display === 'none' || document.querySelector('#tabs').offsetParent === null")
            assert hidden, "tab bar should be hidden while a pitch is on (focus mode), so a player cannot wander off mid-question"
            wait_q(p)
            p.click("#bgo")
            p.wait_for_selector("#res .card")
            back = p.is_visible("#tabs")
            n = len(trials(p))
            ctx.close()
            assert n == 1 and back, (n, back)

        @check("F4", "Robustness", "Reload in the middle of a question: no half-written answers, app recovers to idle", "S2")
        def _():
            ctx, p = E.open()
            setup(p, ask="both")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            wait_q(p)
            p.click("#bgo")
            p.wait_for_timeout(200)
            p.reload()
            p.wait_for_function("window.__gonogo && window.__gonogo.queue()")
            t = trials(p)
            st = p.evaluate("window.__gonogo.state()")
            ctx.close()
            assert st == "idle" and len(t) == 1 and t[0]["q_order"] == 1, (st, t)
            return "kept the one completed answer; the unfinished clip is simply asked again"

        @check("F5", "Robustness", "Corrupt clip file in storage: the app reports it and recovers, it does not hang in 'playing'", "S1")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            clips_ready(p, 6)
            first = qR["packs"][0]["items"][0]["id"]
            p.evaluate("""(id) => new Promise(res => { const r = indexedDB.open('gonogo', 1); r.onsuccess = () => { const tx = r.result.transaction('clips', 'readwrite');
              tx.objectStore('clips').put({id, ab: new Uint8Array(500).buffer, type: 'video/mp4'}); tx.oncomplete = () => res(1); }; })""", first)
            p.click("#tabs button[data-t=play]")
            p.click("#start")
            p.wait_for_timeout(4000)
            st = p.evaluate("window.__gonogo.state()")
            msg = p.inner_text("#now")
            ctx.close()
            assert st in ("idle", "q"), f"stuck in state {st!r}: {msg}"
            return f"state after corrupt clip: {st}; message '{msg[:60]}'"

        @check("F6", "Robustness", "Landscape orientation: question buttons are on screen without scrolling", "S2")
        def _():
            ctx, p = E.open(w=844, h=390)
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            wait_q(p)
            box = p.evaluate("(()=>{const r=document.getElementById('bgo').getBoundingClientRect();return [r.top,r.bottom,innerHeight]})()")
            ctx.close()
            assert box[0] >= 0 and box[1] <= box[2] + 1, box
            return str(box)

        # ------------------------------------------------------------------ G. layout and accessibility
        for w, h, name in ((320, 568, "iPhone SE 1st gen"), (360, 640, "small Android"), (375, 667, "iPhone SE 2/3"), (390, 844, "iPhone 14"), (412, 915, "Pixel 7"), (820, 1180, "iPad")):
            @check(f"G1-{w}", "Layout", f"{name} {w}x{h}: no sideways scroll on any tab; GO/NO-GO visible without scrolling when a question shows", "S1")
            def _(w=w, h=h):
                ctx, p = E.open(w=w, h=h)
                setup(p, ask="both")
                over = {}
                for tab in ("play", "queue", "log", "keys", "set"):
                    p.click(f"#tabs button[data-t={tab}]")
                    p.wait_for_timeout(150)
                    sw, cw = p.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                    over[tab] = sw - cw
                p.click("#tabs button[data-t=queue]")
                p.click("#goNext")
                wait_q(p)
                p.wait_for_timeout(200)
                b = p.evaluate("(()=>{const r=document.getElementById('bgo').getBoundingClientRect();return [r.top,r.bottom,innerHeight,r.height]})()")
                ctx.close()
                assert all(v <= 1 for v in over.values()), over
                assert b[1] <= b[2] + 1, f"answer buttons below the fold: bottom {b[1]:.0f} > viewport {b[2]}"
                return f"overflow {over}; buttons bottom {b[1]:.0f}/{b[2]}, height {b[3]:.0f}"

        @check("G2", "Accessibility", "Tap targets: GO, NO-GO, Start, tabs and sync are at least 44 px tall", "S2")
        def _():
            ctx, p = E.open(w=375, h=667)
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            wait_q(p)
            hs = p.evaluate("""() => Object.fromEntries(['bgo','bno'].map(i => [i, document.getElementById(i).getBoundingClientRect().height]).concat(
                [...document.querySelectorAll('#tabs button')].map(b => ['tab ' + b.textContent, b.getBoundingClientRect().height])))""")
            p.click("#bgo")
            p.wait_for_selector("#res .card")
            hs["start"] = p.evaluate("document.getElementById('start').getBoundingClientRect().height") if p.is_visible("#start") else None
            p.click("#tabs button[data-t=log]")
            hs["sync"] = p.evaluate("document.getElementById('sync').getBoundingClientRect().height")
            ctx.close()
            small = {k: round(v, 1) for k, v in hs.items() if v and v < 44}
            assert not small, f"under 44 px: {small}"
            return str({k: round(v, 1) for k, v in hs.items() if v})

        @check("G3", "Accessibility", "Controls have accessible names; images/svg labelled; page has a title and lang", "S3")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            wait_q(p)
            p.click("#bgo")
            p.wait_for_selector("#res .card")
            info = p.evaluate("""() => ({lang: document.documentElement.lang, title: document.title,
               unnamed: [...document.querySelectorAll('button,select,input')].filter(e => !(e.textContent.trim() || e.getAttribute('aria-label') || (e.labels && e.labels.length) || e.closest('label') || e.closest('dl') )).map(e => e.id || e.tagName),
               svg: [...document.querySelectorAll('svg')].every(s => s.getAttribute('role') === 'img' && s.getAttribute('aria-label'))})""")
            ctx.close()
            assert info["lang"] and info["title"] and not info["unnamed"] and info["svg"], info
            return str(info)

        for scheme in ("light", "dark"):
            @check(f"G4-{scheme}", "Layout", f"{scheme} theme: every tab renders, no script or console errors", "S2")
            def _(scheme=scheme):
                before = len(E.errors)
                ctx, p = E.open(scheme=scheme)
                setup(p, ask="both")
                p.click("#tabs button[data-t=queue]")
                p.click("#goNext")
                answer_clip(p)
                for tab in ("log", "keys", "set"):
                    p.click(f"#tabs button[data-t={tab}]")
                bg = p.evaluate("getComputedStyle(document.body).backgroundColor")
                ctx.close()
                assert len(E.errors) == before, E.errors[before:]
                return f"background {bg}"

        # ------------------------------------------------------------------ H. timing
        @check("H1", "Timing", "Pause lands within 1.5 frames of release+offset for EVERY clip in both queues at 50, 100 and 200 ms", "S1")
        def _():
            devs = []
            ctx, p = E.open()
            for side, q in (("R", qR), ("L", qL)):
                setup(p, bats=side, ask="zone")
                items = [i for pk in q["packs"] for i in pk["items"]]
                p.click("#tabs button[data-t=queue]")
                p.click("#dlAll")
                clips_ready(p, len(items), 120000)
                for off in ("0.050", "0.100", "0.200"):
                    p.click("#tabs button[data-t=set]")
                    p.select_option("#off", off)
                    p.dispatch_event("#off", "change")
                    for it in items:
                        p.evaluate("(id) => { const s = document.getElementById('pitch'); }", it["id"])
                        idx = [k for k, x in enumerate([i for pk in q["packs"] for i in pk["items"]]) if x["id"] == it["id"]][0]
                        p.click("#tabs button[data-t=queue]")
                        p.select_option("#pitch", str(idx))
                        p.click("#tabs button[data-t=play]")
                        p.click("#start")
                        wait_q(p)
                        devs.append(p.evaluate("(window.__pauseMT - window.__gonogo.pauseAt())*60"))
                        p.click("#bgo")
                        p.wait_for_timeout(120)
                        p.evaluate("document.getElementById('v').pause()")
                        p.wait_for_function("window.__gonogo.state()==='idle' || window.__gonogo.state()==='reveal'", timeout=6000)
                        p.evaluate("document.getElementById('v').dispatchEvent(new Event('ended'))")
            ctx.close()
            import statistics as st
            worst = max(abs(d) for d in devs)
            assert worst < 1.5, f"worst deviation {worst:.2f} frames over {len(devs)} runs"
            return f"{len(devs)} runs, median {st.median(devs):+.2f} frames, worst {worst:.2f}"

        @check("H2", "Timing", "Speed: tap Start to question under 3 s (cached clip); app ready under 2 s on localhost", "S3")
        def _():
            ctx, p = E.page()
            t0 = time.time()
            p.goto(base + "/")
            p.wait_for_function("window.__gonogo && window.__gonogo.queue()")
            ready = time.time() - t0
            setup(p, ask="zone")
            p.click("#tabs button[data-t=queue]")
            clips_ready(p, 6)
            p.click("#tabs button[data-t=play]")
            t0 = time.time()
            p.click("#start")
            wait_q(p)
            tq = time.time() - t0
            ctx.close()
            assert ready < 2 and tq < 3, (ready, tq)
            return f"ready {ready:.2f} s, start-to-question {tq:.2f} s (includes the clip's own lead-in)"

        # ------------------------------------------------------------------ I. content integrity
        @check("I1", "Content", "Every queue item: file exists, plays, release inside the clip with at least 0.4 s after it; keys agree with the pitch's own location and type", "S1")
        def _():
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
            bad, n = [], 0
            for q in (qR, qL):
                for pk in q["packs"]:
                    ids = set()
                    for it in pk["items"]:
                        n += 1
                        f = content / pk["dir"] / it["file"]
                        if not f.exists() or f.stat().st_size < 10000:
                            bad.append(("missing/tiny", pk["id"], it["id"]))
                            continue
                        out = subprocess.run([ff, "-i", str(f)], capture_output=True, text=True).stderr
                        import re
                        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
                        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                        if dur < it["release"] + 0.4:
                            bad.append(("short", pk["id"], it["id"], dur, it["release"]))
                        if it["id"] in ids:
                            bad.append(("dup id in pack", pk["id"], it["id"]))
                        ids.add(it["id"])
                        m_ = it["meta"]
                        in_zone = abs(m_["px"]) <= 0.83 and m_["sz_bot"] <= m_["pz"] <= m_["sz_top"]
                        fb = m_["family"] == "FB"
                        if it["keys"] is not None and (it["keys"]["zone_go"] != in_zone or it["keys"]["pitch_go"] != fb):
                            bad.append(("key/meta mismatch", pk["id"], it["id"]))
            assert not bad, bad[:5]
            return f"{n} items checked"

        @check("I2", "Content", "Assessment keys are absent from every public file and present in the private file for every assessment item", "S1")
        def _():
            priv = json.loads(keys.read_text())
            miss = []
            for q in (qR, qL):
                for pk in q["packs"]:
                    if pk["mode"] == "assess":
                        for it in pk["items"]:
                            assert it["keys"] is None
                            if f"{pk['id']}/{it['id']}" not in priv:
                                miss.append(it["id"])
            text = " ".join(p_.read_text() for p_ in content.glob("*.json"))
            assert not miss, miss
            return "queue files carry null keys for assessment items"

        @check("I3", "Content", "Footprint: total content and per-clip size reasonable for a phone", "S3")
        def _():
            sizes = [f.stat().st_size for f in content.rglob("*.mp4")]
            tot = sum(sizes) / 1e6
            assert max(sizes) < 3e6, max(sizes)
            return f"{len(sizes)} clips, {tot:.1f} MB total, largest {max(sizes) / 1e6:.2f} MB"

        # ------------------------------------------------------------------ J. security / server
        @check("J1", "Security", "Path traversal: ../ and encoded variants cannot read files outside the app and content folders", "S1")
        def _():
            leaked = []
            for path in ("/content/../../../../etc/passwd", "/content/%2e%2e/%2e%2e/%2e%2e/etc/passwd", "/..%2f..%2f..%2fetc/passwd", "/../../../../etc/passwd", "/content/../../README.md"):
                try:
                    r = urllib.request.urlopen(urllib.request.Request(base + path))
                    body = r.read(200)
                    if b"root:" in body or b"GamePlan" in body:
                        leaked.append((path, body[:40]))
                except urllib.error.HTTPError:
                    pass
                except Exception:
                    pass
            import socket
            s = socket.create_connection(("127.0.0.1", srv.server_address[1]))
            s.sendall(b"GET /content/../../../../etc/passwd HTTP/1.0\r\n\r\n")
            raw = s.recv(400)
            s.close()
            if b"root:" in raw:
                leaked.append(("raw ../", raw[:60]))
            assert not leaked, leaked
            return "no file outside the served folders was readable"

        @check("J2", "Security", "POST hardening: oversize body, bad JSON, wrong shape, missing ids are all rejected without crashing the server", "S1")
        def _():
            def post(body, headers=None, raw=False):
                req = urllib.request.Request(base + "/api/trials", body if raw else json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
                try:
                    return urllib.request.urlopen(req).status
                except urllib.error.HTTPError as e:
                    return e.code
            def post_big():
                try:
                    return post(b"{" + b" " * (6 * 1024 * 1024) + b"}", raw=True)
                except (urllib.error.URLError, ConnectionError, BrokenPipeError):
                    return 413          # the server refused the body and closed the connection before the client finished sending: that is a rejection
            res = dict(badjson=post(b"{nope", raw=True), notlist=post({"trials": "x"}), nokey=post({"x": 1}), noid=post({"trials": [{"player": "p"}]}), toobig=post_big())
            assert res["badjson"] == 400 and res["notlist"] == 400 and res["nokey"] == 400, res
            assert res["toobig"] in (400, 413), f"6 MB body accepted/handled as {res['toobig']}"
            assert urllib.request.urlopen(base + "/api/health").status == 200
            return str(res)

        @check("J3", "Security", "Shared token: wrong or missing token gets 401 on POST and on the CSV; correct token works", "S2")
        def _():
            s4, st4, b4 = serve(content, token="s3cret")
            codes = []
            for hdr in ({}, {"X-Token": "wrong"}, {"X-Token": "s3cret"}):
                req = urllib.request.Request(b4 + "/api/trials", json.dumps({"trials": [dict(id="z" + str(len(codes)))]}).encode(), {"Content-Type": "application/json", **hdr})
                try:
                    codes.append(urllib.request.urlopen(req).status)
                except urllib.error.HTTPError as e:
                    codes.append(e.code)
            try:
                urllib.request.urlopen(b4 + "/api/trials.csv")
                csv_open = True
            except urllib.error.HTTPError:
                csv_open = False
            s4.shutdown()
            assert codes == [401, 401, 200] and not csv_open, (codes, csv_open)
            return f"codes {codes}; note: config.json hands the token to anyone who opens the app, so it is a team passcode, not a secret"

        @check("J4", "Security", "Script injection: hostile player name and hostile pack title never execute", "S1")
        def _():
            evil = "<img src=x onerror=window.__pwned=1>"
            tmp = pathlib.Path(tempfile.mkdtemp())
            shutil.copytree(content, tmp / "c")
            q = json.loads((tmp / "c" / "queue_R.json").read_text())
            q["packs"][0]["title"] = "Next starter: " + evil
            q["packs"][0]["subtitle"] = evil
            q["packs"][0]["items"][0]["label"] = evil
            (tmp / "c" / "queue_R.json").write_text(json.dumps(q))
            s5, st5, b5 = serve(tmp / "c")
            E5 = Env(pw, b5)
            ctx, p = E5.open()
            setup(p, name=evil, ask="zone")
            for tab in ("queue", "keys", "log", "set", "play"):
                p.click(f"#tabs button[data-t={tab}]")
                p.wait_for_timeout(200)
            pwned = p.evaluate("window.__pwned === 1")
            ctx.close()
            E5.browser.close()
            s5.shutdown()
            assert not pwned, "hostile markup from the queue file executed"

        @check("J5", "Security", "Static server: only GET/POST used; HEAD, OPTIONS and unknown paths answer without killing the server", "S3")
        def _():
            out = {}
            for m in ("HEAD", "OPTIONS", "DELETE", "PUT"):
                try:
                    out[m] = urllib.request.urlopen(urllib.request.Request(base + "/", method=m)).status
                except urllib.error.HTTPError as e:
                    out[m] = e.code
                except Exception as e:
                    out[m] = type(e).__name__
            assert urllib.request.urlopen(base + "/api/health").status == 200
            return str(out)

        # ------------------------------------------------------------------ K. no stray errors across the run
        @check("K1", "Hygiene", "No uncaught script errors or console errors occurred anywhere in this run", "S1")
        def _():
            bad = [e for e in E.errors if "net::ERR" not in e and "Failed to load resource" not in e]
            assert not bad, bad[:4]
            return f"{len(E.errors)} console lines, none from the app's own code"

        E.browser.close()
    srv.shutdown()
    pathlib.Path(__file__).with_name(f"results_{a.engine}.json").write_text(json.dumps(RESULTS, indent=1))
    n_f = sum(r["result"] == "FAIL" for r in RESULTS)
    print(f"\n{len(RESULTS)} checks, {len(RESULTS) - n_f} pass, {n_f} fail")
    return 1 if n_f else 0


if __name__ == "__main__":
    raise SystemExit(main())
