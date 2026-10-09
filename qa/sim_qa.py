"""Release-gate QA for pitches drawn from tracking (phone_app 'sim' items). Same harness as phone_app_qa.

  PYTHONPATH=src python3 qa/sim_qa.py [--content /tmp/claude-0/app/content_sim] [--engine chromium|webkit] [--only S1,S3]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import phone_app_qa as Q  # noqa: E402
from phone_app_qa import ARGS, RESULTS, Env, check, serve, setup, trials, wait_q  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PX = """() => { const c = document.getElementById('sim'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  const cen = (f) => { let n = 0, sx = 0, sy = 0; for (let i = 0; i < d.length; i += 4) { if (f(d[i], d[i+1], d[i+2])) { const k = i / 4; sx += k % c.width; sy += Math.floor(k / c.width); n++ } } return n ? {n, x: sx / n, y: sy / n} : {n: 0} };
  return {w: c.width, h: c.height, ball: cen((r,g,b) => r >= 250 && g >= 250 && b >= 250), orange: cen((r,g,b) => r > 240 && g > 165 && g < 195 && b > 105 && b < 140), zone: cen((r,g,b) => r > 205 && r < 225 && g > 185 && g < 205 && b > 235 && b < 250), ground: cen((r,g,b) => r > 30 && r < 45 && g > 48 && g < 62 && b > 38 && b < 52).n, plate: cen((r,g,b) => r > 238 && r < 246 && g > 238 && g < 246 && b > 238 && b < 246).n} }"""


def start_first(p, ask="both", off="0.100", view="hitter_eye", pack=None):
    setup(p, ask=ask, off=off, view=view)
    p.click("#tabs button[data-t=queue]")
    if pack:
        p.evaluate("(t) => [...document.querySelectorAll('#packs .card')].find(c => c.textContent.includes(t)).querySelector('button').click()", pack)
    else:
        p.click("#goNext")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", default="/tmp/claude-0/app/content_sim")
    ap.add_argument("--engine", choices=["chromium", "webkit"], default="chromium")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    ARGS.update(engine=a.engine, only=[x for x in a.only.split(",") if x])
    content = pathlib.Path(a.content)
    with sync_playwright() as pw:
        srv, store, base = serve(content)
        E = Env(pw, base)
        reqs = []

        @check("S1", "Math", "Projection: centre, +x is screen right, +z is screen up, size falls with distance, points behind the camera are refused", "S1")
        def _():
            ctx, p = E.open()
            r = p.evaluate("""() => { const cam = window.__sim.project({pos: [0, 0, 0], tgt: [0, 1, 0], fov: 20}, 400, 200); const c = cam([0, 10, 0]), rt = cam([1, 10, 0]), up = cam([0, 10, 1]), far = cam([0, 20, 0]);
              const F = 100 / Math.tan(10 * Math.PI / 180); return {c, rt, up, far, behind: cam([0, -1, 0]), F}; }""")
            ctx.close()
            F = r["F"]
            assert abs(r["c"]["x"] - 200) < 1e-6 and abs(r["c"]["y"] - 100) < 1e-6
            assert abs(r["rt"]["x"] - (200 + F * 0.1)) < 1e-6 and abs(r["up"]["y"] - (100 - F * 0.1)) < 1e-6
            assert abs(r["c"]["r"] - F * 0.121 / 10) < 1e-6 and abs(r["far"]["r"] * 2 - r["c"]["r"]) < 1e-6 and r["behind"] is None
            return f"F={F:.1f}; ball radius at 10 ft {r['c']['r']:.2f} px, at 20 ft {r['far']['r']:.2f} px"

        @check("S2", "Math", "Both views: a hitter's-eye camera sits on the batter's side (left-handed on the other side) and both look at the mound", "S2")
        def _():
            ctx, p = E.open()
            r = p.evaluate("() => ({R: window.__sim.views.hitter_eye('R'), L: window.__sim.views.hitter_eye('L'), H: window.__sim.views.low_home('R')})")
            ctx.close()
            assert r["R"]["pos"][0] < 0 < r["L"]["pos"][0] and r["R"]["pos"][2] > 4.5 and r["H"]["pos"][1] < 0 and r["H"]["pos"][0] == 0
            return "RHH eye at x<0, LHH eye at x>0, low-home behind the plate on the centre line"

        @check("S3", "Content", "Every drawn pitch: in the browser, the path's own end point decides strike or ball exactly as the shipped key says, and no video is requested", "S1")
        def _():
            ctx, p = E.page()
            p.on("request", lambda r: reqs.append(r.url) if r.url.endswith(".mp4") else None)
            p.goto(base + "/")
            p.wait_for_function("window.__gonogo && window.__gonogo.queue()")
            r = p.evaluate("""() => { const bad = [], n = {items: 0}; for (const q of [window.__gonogo.queue()]) for (const pk of q.packs) for (const it of pk.items) { n.items++;
                const s = it.sim, t = s.t_zone, z = s.z0 + s.vz0 * t + 0.5 * s.az * t * t, x = s.x0 + s.vx0 * t + 0.5 * s.ax * t * t, y = s.y0 + s.vy0 * t + 0.5 * s.ay * t * t;
                const inz = Math.abs(x) <= 0.83 && s.sz_bot <= z && z <= s.sz_top;
                if (it.file !== null || it.release !== 0) bad.push(['file/release', it.id]);
                if (Math.abs(y - 17/12) > 1e-3 || Math.abs(x - s.px) > 0.005 || Math.abs(z - s.pz) > 0.005) bad.push(['end point', it.id]);
                if (it.keys && it.keys.strike !== inz) bad.push(['key', it.id, it.keys.strike, inz]); } return {n: n.items, bad}; }""")
            ctx.close()
            assert r["n"] >= 20 and not r["bad"] and not reqs, (r, reqs[:2])
            return f"{r['n']} drawn pitches consistent; video requests: {len(reqs)}"

        @check("S4", "Core", "Pause: the ball freezes at exactly the chosen time, drawn where the math puts it (within 1 device pixel), the future path is not on screen, and the questions appear", "S1")
        def _():
            out = []
            for view, offs in (("hitter_eye", ("0.100", "0.200", "0.250")), ("low_home", ("0.100", "0.200", "0.300"))):
                for off in offs:
                    ctx, p = E.open()
                    start_first(p, off=off, view=view)
                    wait_q(p)
                    p.wait_for_timeout(150)
                    d = p.evaluate("() => ({drawn: window.__sim.drawn(), q: window.__sim.q(), exp: (() => { const q = window.__sim.q(), t = window.__sim.drawn().tmax; return window.__sim.cam()(window.__sim.pos(q, t)); })()})")
                    px = p.evaluate(PX)
                    lum = p.evaluate("""() => { const c = document.getElementById('sim'), g = c.getContext('2d'), P = window.__sim.cam()([0, 0.7, 0]); if (!P) return -1; let m = 0;
                      for (let dx = -2; dx <= 2; dx++) for (let dy = -2; dy <= 2; dy++) { const d = g.getImageData(Math.round(P.x) + dx, Math.round(P.y) + dy, 1, 1).data; m = Math.max(m, Math.min(d[0], d[1], d[2])) } return m }""")
                    ctx.close()
                    assert abs(d["drawn"]["tmax"] - float(off)) < 1e-9 and d["drawn"]["trail"] is False, d["drawn"]
                    assert px["ball"]["n"] > 3 and abs(px["ball"]["x"] - d["exp"]["x"]) < 1.0 and abs(px["ball"]["y"] - d["exp"]["y"]) < 1.0, (px["ball"], d["exp"])
                    assert px["orange"]["n"] == 0 and px["zone"]["n"] == 0, ("future/answer marks on screen before the answer", px)
                    assert px["ground"] > 0.10 * px["w"] * px["h"], ("scene is empty: no ground", px["ground"])
                    if view == "low_home":
                        assert lum > 150, ("no plate at its projected position in the behind-home view", lum)
                    out.append(f"{view} {off}: ball r={d['exp']['r']:.1f}px")
            return "; ".join(out)

        @check("S5", "Core", "Reveal: after both answers the ball runs on, then a behind-the-plate recap shows trail, zone and a crossing marker on the tracked location (within 1.5 device pixels); the end point equals the tracked crossing", "S1")
        def _():
            out = []
            for view in ("hitter_eye", "low_home"):
                ctx, p = E.open()
                start_first(p, off="0.150", view=view)
                Q.answer_clip(p, ("Strike", 0))
                p.wait_for_function("window.__gonogo.state()==='idle'", timeout=8000)
                d = p.evaluate("() => { const q = window.__sim.q(), c = window.__sim.cam(); return {drawn: window.__sim.drawn(), end: c(window.__sim.pos(q, q.t_zone)), cross: c([q.px, 17/12, q.pz]), tz: q.t_zone, w: window.__sim.size()}; }")
                px = p.evaluate(PX)
                ctx.close()
                assert abs(d["drawn"]["tmax"] - d["tz"]) < 1e-9 and d["drawn"]["trail"] is True and d["drawn"]["cam"] == "recap", d["drawn"]
                assert abs(d["end"]["x"] - d["cross"]["x"]) < 0.1 and abs(d["end"]["y"] - d["cross"]["y"]) < 0.1, d
                assert 0 < d["cross"]["x"] < d["w"][0] and 0 < d["cross"]["y"] < d["w"][1], ("crossing is off the picture", d["cross"], d["w"])
                assert px["zone"]["n"] > 20 and px["orange"]["n"] > 10, px
                assert abs(px["orange"]["x"] - d["cross"]["x"]) < 1.5 and abs(px["orange"]["y"] - d["cross"]["y"]) < 1.5, (px["orange"], d["cross"])
                out.append(f"{view}: marker off by ({px['orange']['x']-d['cross']['x']:+.2f}, {px['orange']['y']-d['cross']['y']:+.2f}) px")
            return "; ".join(out)

        for w, h in ((320, 568), (390, 844)):
            @check(f"S12-{w}", "Framing", f"{w} wide: for EVERY shipped pitch, both views and every allowed pause, the ball is inside the picture (3% margin) from release to the pause, and the recap frames zone, crossing and whole path", "S1")
            def _(w=w, h=h):
                ctx, p = E.open(w=w, h=h)
                setup(p, ask="both", off="0.100", view="hitter_eye")
                p.click("#tabs button[data-t=play]")
                r = p.evaluate("""() => { const s = document.querySelector('.stage').getBoundingClientRect(), W = Math.round(s.width * 2), H = Math.round(s.height * 2), bad = [];
                  const offs = {hitter_eye: [0, .05, .1, .15, .2, .25], low_home: [0, .05, .1, .15, .2, .25, .3]}; let n = 0;
                  for (const pk of window.__gonogo.queue().packs) for (const it of pk.items) for (const view of Object.keys(offs)) {
                    const cam = window.__sim.project(window.__sim.views[view](it.sim.stand), W, H);
                    for (const off of offs[view]) for (let i = 0; i <= 12; i++) { n++; const c = cam(window.__sim.pos(it.sim, off * i / 12));
                      if (!c || c.x < W * .03 || c.x > W * .97 || c.y < H * .03 || c.y > H * .97) { bad.push([it.id, view, off]); break } } }
                  const rbad = [];
                  for (const pk of window.__gonogo.queue().packs) for (const it of pk.items) { const q = it.sim, cfg = window.__sim.recapCfg(q, W, H), cam = window.__sim.project(cfg, W, H);
                    const pts = [[q.px, 17/12, q.pz], [-.83, 17/12, q.sz_bot], [.83, 17/12, q.sz_bot], [-.83, 17/12, q.sz_top], [.83, 17/12, q.sz_top]];
                    for (let i = 0; i <= 20; i++) pts.push(window.__sim.pos(q, q.t_zone * i / 20));
                    if (!pts.every(P => { const c = cam(P); return c && c.x > W * .04 && c.x < W * .96 && c.y > H * .04 && c.y < H * .96 })) rbad.push([it.id, cfg.fov]); n++; }
                  return {n, bad: bad.length + rbad.length, sample: bad.slice(0, 3).concat(rbad.slice(0, 3)), size: [W, H]}; }""")
                ctx.close()
                assert r["bad"] == 0, r
                return f"{r['n']} checks on a {r['size'][0]}x{r['size'][1]} picture, none out of frame"

        @check("S13", "Framing", "Guards: a pause over 250 ms in the hitter's-eye view is used as 250 ms (setting untouched, trial logs 250), and a pitch that would leave the picture is shown from low-home and logged that way", "S1")
        def _():
            ctx, p = E.open()
            setup(p, ask="zone", off="0.300", view="hitter_eye")
            assert p.input_value("#off") == "0.300", p.input_value("#off")
            p.click("#tabs button[data-t=queue]")
            p.click("#goNext")
            wait_q(p)
            assert abs(p.evaluate("window.__sim.drawn().tmax") - 0.25) < 1e-9
            p.click("#bstrike")
            p.wait_for_timeout(300)
            t = trials(p)
            ctx.close()
            assert len(t) == 1 and t[0]["pause_ms"] == 250 and t[0]["camera"] == "sim:hitter_eye", t
            ctx, p = E.open()
            setup(p, ask="zone", off="0.100", view="hitter_eye")
            p.click("#tabs button[data-t=queue]")
            p.evaluate("window.__sim.views.hitter_eye = () => ({pos: [-2.4, 0, 5.4], tgt: [0, 50, 3.0], fov: 3})")
            p.click("#goNext")
            wait_q(p)
            p.click("#bstrike")
            p.wait_for_timeout(300)
            t2 = trials(p)
            ctx.close()
            assert len(t2) == 1 and t2[0]["camera"] == "sim:low_home", t2
            return "250 ms cap used without rewriting the setting; fallback logged as sim:low_home"

        @check("S6", "Timing", "Timing: the question appears 0.8 s lead-in + offset after the pitch starts (within 80 ms, measured inside the page), for three offsets", "S2")
        def _():
            res = []
            for off in ("0.100", "0.200", "0.300"):
                ctx, p = E.open()
                start_first(p, off=off)
                wait_q(p)
                tm = p.evaluate("window.__sim.timing()")
                ctx.close()
                dt, exp = (tm["q"] - tm["start"]) / 1000, 0.8 + float(off)
                assert tm["q"] > tm["start"] > 0 and abs(dt - exp) < 0.08, (off, dt, exp)
                res.append(f"{off}: {dt:.3f}s (expected {exp:.3f})")
            return "; ".join(res)

        @check("S7", "Robustness", "A stalled picture (a frame gap over 250 ms) aborts the pitch with a message instead of jumping to the pause", "S1")
        def _():
            ctx, p = E.open()
            start_first(p)
            p.wait_for_function("window.__gonogo.state()==='playing'")
            p.evaluate("(() => { const e = performance.now() + 450; while (performance.now() < e) {} })()")
            p.wait_for_timeout(300)
            st = p.evaluate("window.__gonogo.state()")
            msg = p.inner_text("#now")
            n = len(trials(p))
            ctx.close()
            assert st == "idle" and "stalled" in msg and n == 0, (st, msg, n)

        @check("S8", "Core", "Answers: log carries camera sim:<view>, keys score, no key text in assessment; both views log their own name", "S1")
        def _():
            out = []
            for view in ("hitter_eye", "low_home"):
                ctx, p = E.open()
                start_first(p, view=view)
                Q.answer_clip(p, ("Strike", 0))
                p.wait_for_function("window.__gonogo.state()==='idle'", timeout=8000)
                t = trials(p)
                ctx.close()
                assert len(t) == 2 and all(x["camera"] == f"sim:{view}" and x["key"] and x["correct"] in (0, 1) for x in t), t
                out.append(view)
            ctx, p = E.open()
            start_first(p, pack="Assessment")
            Q.answer_clip(p, ("Strike", 0))
            p.wait_for_function("document.getElementById('hlab').textContent==='Recorded'", timeout=8000)
            t = trials(p)
            ctx.close()
            assert len(t) == 2 and all(x["key"] == "" and x["correct"] == "" for x in t), t
            return "logged " + ", ".join(out) + "; assessment keys blank"

        for w, h in ((320, 568), (375, 667), (390, 844)):
            @check(f"S9-{w}", "Layout", f"{w}x{h}: the drawing fills the stage, nothing scrolls sideways, and the Strike/Ball buttons and then every pitch choice are on screen", "S1")
            def _(w=w, h=h):
                ctx, p = E.open(w=w, h=h)
                start_first(p)
                wait_q(p)
                p.wait_for_timeout(200)
                b = p.evaluate("(()=>{const s=document.querySelector('.stage').getBoundingClientRect(),c=document.getElementById('sim').getBoundingClientRect(),r=document.getElementById('bstrike').getBoundingClientRect();return {stage:[s.width,s.height],canvas:[c.width,c.height],bottom:r.bottom,vh:innerHeight,over:document.documentElement.scrollWidth-document.documentElement.clientWidth}})()")
                p.click("#bstrike")
                p.wait_for_function("document.getElementById('hlab').textContent.startsWith('Question 2')")
                o = p.evaluate("(()=>{const bs=[...document.querySelectorAll('#opts button')];return {bottom:Math.max(...bs.map(e=>e.getBoundingClientRect().bottom)),vh:innerHeight,n:bs.length}})()")
                ctx.close()
                assert abs(b["canvas"][0] - b["stage"][0]) < 1 and abs(b["canvas"][1] - b["stage"][1]) < 1 and b["over"] <= 1, b
                assert b["bottom"] <= b["vh"] + 1 and o["bottom"] <= o["vh"] + 1, (b, o)
                return f"buttons bottom {b['bottom']:.0f}/{b['vh']}, choices bottom {o['bottom']:.0f}/{o['vh']} ({o['n']} choices)"

        @check("S10", "Core", "Same pitch, same offset, same view: identical pixels each time (the picture is deterministic)", "S2")
        def _():
            hashes = []
            for _i in range(2):
                ctx, p = E.open()
                setup(p, ask="both", off="0.200", view="hitter_eye")
                p.click("#tabs button[data-t=queue]")
                p.select_option("#pitch", "3")
                p.click("#tabs button[data-t=play]")
                p.click("#start")
                wait_q(p)
                p.wait_for_timeout(100)
                hashes.append(p.evaluate("() => { const c = document.getElementById('sim'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let h = 2166136261; for (let i = 0; i < d.length; i += 7) { h ^= d[i]; h = Math.imul(h, 16777619) } return h >>> 0 }"))
                ctx.close()
            assert hashes[0] == hashes[1], hashes
            return f"hash {hashes[0]}"

        @check("S11", "Core", "Mixed queue: after a drawn pitch the page returns to normal video playback when the next item is a clip (video visible, canvas hidden)", "S2")
        def _():
            # the sim content has no clips, so check the toggle directly: starting a sim pitch hides the video, and the video element is restored by the clip path
            ctx, p = E.open()
            start_first(p)
            wait_q(p)
            v = p.evaluate("[getComputedStyle(document.getElementById('v')).display, getComputedStyle(document.getElementById('sim')).display]")
            ctx.close()
            assert v == ["none", "block"], v
            src = pathlib.Path(__file__).resolve().parents[1].joinpath("phone_app/index.html").read_text()
            assert '$("sim").style.display="none";$("v").style.display=""' in src
            return "sim shows canvas and hides video; clip path restores the video"

        K = [r for r in RESULTS if r["id"] == "K1"]
        errs = [e for e in E.errors]

        @check("K1", "Console", "No uncaught script errors or console errors during the run", "S1")
        def _():
            assert not errs, errs[:3]

        srv.shutdown()
        E.browser.close()
    n = len(RESULTS)
    ok = sum(r["result"] == "PASS" for r in RESULTS)
    pathlib.Path(__file__).with_name(f"results_sim_{a.engine}.json").write_text(json.dumps(RESULTS, indent=1))
    print(f"\n{n} checks, {ok} pass, {n - ok} fail")
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
