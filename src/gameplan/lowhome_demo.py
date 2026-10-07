"""Build a playable go/no-go page from low-home clips: trims each clip around the release found by lowhome_release, embeds the video,
and writes one self-contained HTML file (no server needed, works offline).

The page plays the lead-in, pauses automatically a set time after release (frame-accurate where the browser supports it),
shows Go / No-Go, times the decision, plays the rest, and scores it against an answer key if one is supplied.
Answer keys are never guessed: a pitch with no key is still played and timed, and shows 'no answer key'.
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess

from . import lowhome_release as L
from .videocut import _ffmpeg

LEAD, TAIL = 1.6, 2.0


def trim(src: str, release: float, out: pathlib.Path, codec: str) -> dict:
    start = max(0.0, release - LEAD)
    args = [_ffmpeg(), "-v", "error", "-y", "-i", src, "-ss", f"{start:.3f}", "-to", f"{release + TAIL:.3f}"]
    if codec == "h264":
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]
    else:
        args += ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-deadline", "realtime", "-cpu-used", "8", "-c:a", "libopus", "-b:a", "64k"]
    subprocess.run(args + [str(out)], check=True)
    return dict(release_in_clip=round(release - start, 4), duration=round(min(release + TAIL, 1e9) - start, 3))


def build(clips: list[str], out_html: pathlib.Path, profile: L.CameraProfile, answers: dict | None = None, codec: str = "h264") -> list[dict]:
    work = out_html.parent / "_trim"
    work.mkdir(parents=True, exist_ok=True)
    items = []
    for i, src in enumerate(clips):
        r = L.analyze(src, profile)
        name = pathlib.Path(src).stem
        if r["status"] != "ok":
            print(f"{name}: no package ({r['reason']})")
            continue
        release = r["release_frame"] / r["fps"]
        ext = "mp4" if codec == "h264" else "webm"
        f = work / f"{name}.{ext}"
        meta = trim(src, release, f, codec)
        b64 = base64.b64encode(f.read_bytes()).decode()
        key = (answers or {}).get(name, {})
        items.append(dict(id=name, label=f"Pitch {len(items) + 1}", mime="video/mp4" if codec == "h264" else "video/webm", b64=b64, release=meta["release_in_clip"],
                          release_frame=r["release_frame"], zone_go=key.get("zone_go"), pitch_go=key.get("pitch_go"), result=key.get("result")))
        print(f"{name}: release frame {r['release_frame']} ({release:.3f} s); clip trimmed to {meta['duration']} s, {f.stat().st_size / 1e6:.1f} MB")
    out_html.write_text(PAGE.replace("/*ITEMS*/[]", json.dumps(items)), encoding="utf-8")
    return items


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Go No-Go, Low Home</title>
<style>
:root{--bg:#14101a;--panel:#1d1726;--ink:#f1ecf7;--mute:#a79bb8;--line:#33284a;--accent:#5F249F;--teal:#005F61;--tan:#8F654D;--good:#2fbf8a;--bad:#e5645a}
@media (prefers-color-scheme: light){:root{--bg:#f6f3fa;--panel:#fff;--ink:#1c1428;--mute:#6b5f7c;--line:#ddd3ea}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 "JetBrains Mono",ui-monospace,Menlo,monospace}
.wrap{max-width:1040px;margin:0 auto;padding:16px}
h1{font-size:18px;margin:4px 0 2px}.sub{color:var(--mute);margin:0 0 14px}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
.bar label{color:var(--mute);font-size:13px}
select,button,input{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 10px}
button{cursor:pointer}button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.stage{position:relative;background:#000;border-radius:8px;overflow:hidden;aspect-ratio:16/9}
video{width:100%;height:100%;display:block;object-fit:contain;background:#000}
.overlay{position:absolute;inset:0;display:none;align-items:flex-end;justify-content:center;padding:18px;gap:14px;background:linear-gradient(transparent 55%,rgba(0,0,0,.7))}
.overlay.on{display:flex}
.big{flex:1;max-width:340px;padding:20px 12px;font-size:22px;font-weight:700;border-radius:10px;border:2px solid transparent}
.go{background:var(--teal);color:#fff}.nogo{background:var(--tan);color:#fff}
.hint{position:absolute;top:10px;left:12px;color:#fff;background:rgba(0,0,0,.55);padding:4px 8px;border-radius:6px;font-size:13px;display:none}
.hint.on{display:block}
.result{margin-top:12px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;display:none}
.result.on{display:block}.ok{color:var(--good)}.no{color:var(--bad)}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--mute);font-weight:500}
.keys{margin-top:14px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px}
.keys h2{font-size:14px;margin:0 0 6px}.keys small{color:var(--mute)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0}
@media (max-width:600px){.big{font-size:18px;padding:16px 8px}}
</style></head><body><div class="wrap">
<h1>Go / No-Go, low home</h1>
<p class="sub">The pitch plays, pauses a set time after release, then you decide. Space or Enter starts. G = Go, N = No-Go.</p>
<div class="bar">
  <label>Pitch <select id="pitch"></select></label>
  <label>Task <select id="task"><option value="zone_go">Swing at strikes (zone)</option><option value="pitch_go">Swing at fastballs (pitch type)</option></select></label>
  <label>Pause after release <select id="off"><option value="0.050">50 ms</option><option value="0.080">80 ms</option><option value="0.100" selected>100 ms</option><option value="0.150">150 ms</option><option value="0.200">200 ms</option></select></label>
  <button class="primary" id="start">Start pitch</button>
</div>
<div class="stage"><video id="v" playsinline muted preload="auto"></video><div class="hint" id="hint">Watch the pitch</div>
  <div class="overlay" id="ov"><button class="big go" id="bgo">GO  (G)</button><button class="big nogo" id="bno">NO-GO  (N)</button></div></div>
<div class="result" id="res"></div>
<table id="log"><thead><tr><th>#</th><th>Pitch</th><th>Task</th><th>Pause</th><th>Call</th><th>Decision time</th><th>Answer</th><th>Score</th></tr></thead><tbody></tbody></table>
<div class="row"><button id="copy">Copy log as CSV</button><span id="copied" class="sub"></span></div>
<div class="keys"><h2>Answer keys</h2><small>These clips carry no tracking data. Set the truth for each pitch (from the TrackMan row or the umpire call), or leave it unknown and the page will time your decision without scoring it.</small><div id="keys"></div></div>
</div>
<script>
const ITEMS=/*ITEMS*/[];
const $=id=>document.getElementById(id);
const KEYS_STORE="gonogo_keys_v1";
let keys={};try{keys=JSON.parse(localStorage.getItem(KEYS_STORE)||"{}")}catch(e){}
ITEMS.forEach(it=>{const k=keys[it.id]||{};if(it.zone_go!=null&&k.zone_go==null)(keys[it.id]=keys[it.id]||{}).zone_go=it.zone_go;if(it.pitch_go!=null&&k.pitch_go==null)(keys[it.id]=keys[it.id]||{}).pitch_go=it.pitch_go;});
function saveKeys(){try{localStorage.setItem(KEYS_STORE,JSON.stringify(keys))}catch(e){}}
const urls={};
ITEMS.forEach(it=>{const bin=atob(it.b64);const u8=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);urls[it.id]=URL.createObjectURL(new Blob([u8],{type:it.mime}));it.b64=null;});
const sel=$("pitch");ITEMS.forEach((it,i)=>{const o=document.createElement("option");o.value=i;o.textContent=it.label+"  ("+it.id.slice(0,8)+")";sel.appendChild(o)});
const v=$("v");let state="idle",pauseAt=0,t0=0,log=[],cur=null;
function renderKeys(){const el=$("keys");el.innerHTML="";ITEMS.forEach(it=>{const k=keys[it.id]||{};const d=document.createElement("div");d.className="row";
  const mk=(f,lab)=>{const s=document.createElement("select");[["","unknown"],["true","Go (swing)"],["false","No-Go (take)"]].forEach(([val,txt])=>{const o=document.createElement("option");o.value=val;o.textContent=txt;if(String(k[f])===val||(k[f]==null&&val===""))o.selected=true;s.appendChild(o)});
    s.onchange=()=>{keys[it.id]=keys[it.id]||{};keys[it.id][f]=s.value===""?null:s.value==="true";saveKeys()};const l=document.createElement("label");l.textContent=lab+" ";l.appendChild(s);return l};
  const n=document.createElement("span");n.textContent=it.label;n.style.minWidth="70px";d.append(n,mk("zone_go","Zone task answer"),mk("pitch_go","Pitch task answer"));el.appendChild(d)})}
renderKeys();
function load(){cur=ITEMS[+sel.value];v.src=urls[cur.id];v.muted=true;v.currentTime=0;state="idle";$("ov").classList.remove("on");$("hint").classList.remove("on");$("res").classList.remove("on")}
sel.onchange=load;load();
function watch(){ // frame-accurate pause where requestVideoFrameCallback exists
  if(state!=="playing")return;
  const check=(now,meta)=>{if(state!=="playing")return;const mt=meta?meta.mediaTime:v.currentTime;
    if(mt>=pauseAt-0.0085){window.__pauseMT=mt;v.pause();v.currentTime=pauseAt;prompt();return}
    v.requestVideoFrameCallback?v.requestVideoFrameCallback(check):requestAnimationFrame(()=>check(0,null))};
  v.requestVideoFrameCallback?v.requestVideoFrameCallback(check):requestAnimationFrame(()=>check(0,null))}
function startPitch(){if(state==="playing"||state==="deciding")return;load();pauseAt=cur.release+parseFloat($("off").value);state="playing";$("hint").classList.add("on");$("res").classList.remove("on");v.muted=true;v.currentTime=0;v.play();watch()}
function prompt(){state="deciding";t0=performance.now();$("hint").classList.remove("on");$("ov").classList.add("on")}
function decide(go){if(state!=="deciding")return;const rt=Math.round(performance.now()-t0);state="reveal";$("ov").classList.remove("on");v.muted=false;v.play();
  const task=$("task").value;const key=(keys[cur.id]||{})[task];let score="no key",cls="";if(key!=null){score=(key===go)?"correct":"wrong";cls=key===go?"ok":"no"}
  const row={n:log.length+1,pitch:cur.label,task:task==="zone_go"?"zone":"pitch type",pause:Math.round(parseFloat($("off").value)*1000)+" ms",call:go?"GO":"NO-GO",rt,answer:key==null?"unknown":key?"GO":"NO-GO",score};
  log.push(row);const r=$("res");r.innerHTML=`<b>You said ${row.call}</b> in ${rt} ms. Answer: ${row.answer}. <span class="${cls}"><b>${score.toUpperCase()}</b></span>`;r.classList.add("on");addRow(row)}
function addRow(r){const tb=document.querySelector("#log tbody");const tr=document.createElement("tr");tr.innerHTML=`<td>${r.n}</td><td>${r.pitch}</td><td>${r.task}</td><td>${r.pause}</td><td>${r.call}</td><td>${r.rt} ms</td><td>${r.answer}</td><td>${r.score}</td>`;tb.appendChild(tr)}
$("start").onclick=startPitch;$("bgo").onclick=()=>decide(true);$("bno").onclick=()=>decide(false);
document.addEventListener("keydown",e=>{if(e.target.tagName==="SELECT")return;if(e.key==="g"||e.key==="G")decide(true);else if(e.key==="n"||e.key==="N")decide(false);else if(e.key===" "||e.key==="Enter"){e.preventDefault();startPitch()}});
$("copy").onclick=async()=>{const h="n,pitch,task,pause,call,decision_ms,answer,score";const csv=[h,...log.map(r=>[r.n,r.pitch,r.task,r.pause,r.call,r.rt,r.answer,r.score].join(","))].join("\n");try{await navigator.clipboard.writeText(csv);$("copied").textContent="copied"}catch(e){$("copied").textContent="copy failed";}};
v.addEventListener("ended",()=>{if(state==="reveal")state="idle"});
window.__gonogo={state:()=>state,pauseAt:()=>pauseAt,item:()=>cur,log:()=>log,time:()=>v.currentTime};
</script></body></html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--out", default="/tmp/claude-0/lowhome/demo/gonogo.html")
    ap.add_argument("--codec", choices=("h264", "vp9"), default="h264")
    ap.add_argument("--profile", default="config/lowhome_profiles/visalia_low_home_dev.json")
    ap.add_argument("--answers", default=None, help="JSON {clip_stem: {zone_go: bool, pitch_go: bool}}")
    a = ap.parse_args(argv)
    ans = json.loads(pathlib.Path(a.answers).read_text()) if a.answers else None
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    build(a.clips, out, L.CameraProfile.from_json(pathlib.Path(a.profile).read_text()), ans, a.codec)
    print("wrote", out, f"{out.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
