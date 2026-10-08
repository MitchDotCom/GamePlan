"""Browser test of the phone app against real built content. Skipped when Chromium or built content is absent.
Content: set GONOGO_APP_CONTENT to a directory made by gameplan.app_content (queue_R.json and pack folders)."""
import json
import os
import pathlib
import threading

import pytest

CONTENT = pathlib.Path(os.environ.get("GONOGO_APP_CONTENT", "/tmp/claude-0/app/content"))
CHROME = pathlib.Path("/opt/pw-browsers/chromium-1234/chrome-linux64/chrome")
pytestmark = pytest.mark.skipif(not (CHROME.exists() and (CONTENT / "queue_R.json").exists()), reason="needs Chromium and built content")


def test_phone_flow(tmp_path):
    from playwright.sync_api import sync_playwright
    from gameplan import app_server as AS
    srv, store = AS.serve(CONTENT, tmp_path / "data", 0, None, None)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://localhost:{srv.server_address[1]}"
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=str(CHROME), args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
        p = ctx.new_page()
        errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.goto(base + "/")
        p.wait_for_function("window.__gonogo && window.__gonogo.queue()")
        # player required
        assert p.is_visible("#t-set")
        p.fill("#player", "Test Hitter")
        p.select_option("#bats", "R")
        p.dispatch_event("#player", "change")
        p.click("#tabs button[data-t=queue]")
        assert "Next starter" in p.inner_text("#nextTitle")
        # clips download into IndexedDB
        p.wait_for_function("document.getElementById('dlmsg').textContent.includes('clips on this phone')", timeout=60000)
        p.click("#goNext")
        # both questions per clip, GO then NO-GO
        p.wait_for_function("window.__gonogo.state()==='q'", timeout=20000)
        first = p.inner_text("#hnum")
        assert first in ("Strike?", "Fastball?")
        dev = p.evaluate("(window.__pauseMT - window.__gonogo.pauseAt())*60")
        assert abs(dev) < 1.5                                   # paused within a frame and a half of the target
        p.click("#bgo")
        p.wait_for_function("document.getElementById('hlab').textContent.startsWith('Question 2')")
        second = p.inner_text("#hnum")
        assert {first, second} == {"Strike?", "Fastball?"}
        p.click("#bno")
        p.wait_for_selector("#res .card")
        card = p.inner_text("#res")
        for needle in ("Strike?", "Fastball?", "Pitch", "Where it crossed", "Ride", "Run", "Flight time"):
            assert needle in card, needle
        assert p.is_visible("#res .zonecard svg")
        trials = p.evaluate("window.__gonogo.trials()")
        assert len(trials) == 2 and {t["task"] for t in trials} == {"zone", "pitch"} and trials[0]["clip_trial"] == trials[1]["clip_trial"]
        assert {t["q_order"] for t in trials} == {1, 2} and all(t["pocket"] and t["pitch_type"] for t in trials)
        # sync reaches the server
        p.click("#tabs button[data-t=log]")
        p.click("#sync")
        p.wait_for_function("document.getElementById('syncmsg').textContent.startsWith('Synced')", timeout=10000)
        assert len(store.rows()) == 2
        # offline: reload with no network, the app, queue and clips still work
        p.wait_for_timeout(1500)
        ctx.set_offline(True)
        p.reload()
        p.wait_for_function("window.__gonogo && window.__gonogo.queue()", timeout=10000)
        p.click("#tabs button[data-t=play]")
        p.click("#start")
        p.wait_for_function("window.__gonogo.state()==='q'", timeout=20000)
        assert "offline" in p.inner_text("#net")
        assert errs == []
        b.close()
    srv.shutdown()
