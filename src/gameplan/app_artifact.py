"""Turn phone_app/index.html into a private claude.ai Artifact page: one link that opens on an iPhone with nothing to install or run.

  python -m gameplan.app_artifact --content <dir>/content --out <dir>

Writes <out>/index.html and copies the content under <out>/content so the Artifact tool can publish them as supporting files. What changes from the phone app:
  - no doctype/html/head/body, manifest, apple tags or service worker (the Artifact frame supplies the skeleton and does not allow service workers)
  - fonts come from Google Fonts (the only host the frame allows) instead of the bundled files
  - the safe-area padding is left to the skeleton
  - if the frame refuses blob: video, the clip is played from its own file URL instead
  - answers are written to the artifact's `db` capability (documents trials/<id>); the player, mode and pack are in each document, so they read straight into gameplan.recognition_profile
What it cannot do: install to the home screen, work offline, or let the page score assessment packs (those keys stay with whoever reads the database).
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[2]
FONT = "https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;1,700;1,800&display=swap"


def transform(html: str) -> str:
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    body = re.search(r"<body>(.*?)<script>", html, re.S).group(1)
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)

    def must(pattern_old, new, text, count=1):
        assert text.count(pattern_old) == count, (pattern_old[:70], text.count(pattern_old))
        return text.replace(pattern_old, new)

    # skeleton supplies the safe-area padding; keep the sticky bar clear of the status bar
    style = must("padding:calc(var(--s3) + env(safe-area-inset-top,0px)) 0 var(--s3)", "padding:var(--s3) 0", style)
    style = must("position:sticky;top:0;z-index:5", "position:sticky;top:env(safe-area-inset-top,0px);z-index:5", style)
    style = must("padding:0 var(--s4) calc(var(--s6) + env(safe-area-inset-bottom,0px))", "padding:0 var(--s4) var(--s6)", style)

    # no service worker, no config.json (neither exists in the Artifact frame)
    script = must('  if("serviceWorker"in navigator)navigator.serviceWorker.register("sw.js").catch(()=>{})}', "}", script)
    script = must('try{const r=await fetch("config.json",{cache:"no-cache"});CFG=Object.assign(CFG,await r.json())}catch(e){CFG=Object.assign(CFG,await kvGet("config",{}))}await kvSet("config",CFG);', "", script)

    # blob: video may be refused by the frame; fall back to the clip's own URL once
    script = must('v.addEventListener("error",()=>abortPlay(', 'let triedDirect=false;\nv.addEventListener("error",()=>{if(state==="playing"&&!triedDirect&&cur){triedDirect=true;v.src=CFG.content+curPack.dir+"/"+cur.file;v.play().catch(()=>{});return}abortPlay(', script)
    script = must('"This clip could not be played. Tap Start pitch to try again, or pick another pitch."));', '"This clip could not be played. Tap Start pitch to try again, or pick another pitch.")});', script)
    script = must("urlNow=URL.createObjectURL(clipBlob(c));v.src=urlNow;", "urlNow=URL.createObjectURL(clipBlob(c));triedDirect=false;v.src=urlNow;", script)

    # sync to the artifact database when there is no server
    script = must('async function sync(){if(!CFG.sync_url){say("syncmsg","No sync server is set. Use Download to share the file.");return false}',
                  '''async function dbSync(){let db=null;try{db=window.claude&&await window.claude.use("db")}catch(e){}if(!db)return null;
  const un=(await allTrials()).filter(t=>!t.synced);if(!un.length){say("syncmsg","Nothing to sync.");return true}
  let n=0;try{for(const t of un){await db.doc("trials/"+t.id).set(Object.assign({},t,{synced:1}));t.synced=1;await putTrial(t);n++}say("syncmsg",`Synced ${n}.`);setNet(true);return true}
  catch(e){say("syncmsg",n?`Synced ${n}, then stopped (${e&&e.code||"error"}). It will retry.`:`Sync failed (${e&&e.code||"error"}). It will retry.`);return false}}
async function sync(){if(!CFG.sync_url){const r=await dbSync();if(r!==null)return r;say("syncmsg","Not connected to the sync store. Use Download to share the file.");return false}''', script)
    # the frame blocks plain download links and navigator.share; saving a file goes through the `downloads` capability
    i = script.index('$("dl").onclick=async()=>{')
    j = script.index("a.download=\"gonogo_trials.csv\";a.click()};", i) + len("a.download=\"gonogo_trials.csv\";a.click()};")
    script = script[:i] + '$("dl").onclick=async()=>{let d=null;try{d=window.claude&&await window.claude.use("downloads")}catch(e){}const csv=toCSV(await allTrials());if(!d){say("syncmsg","This view cannot save files. Use Copy log as CSV.");return}try{await d.save({filename:"gonogo_trials.csv",data:csv});say("syncmsg","Saved.")}catch(e){say("syncmsg","Save was cancelled.")}};' + script[j:]
    return (f'<title>Go / No-Go</title>\n<link rel="stylesheet" href="{FONT}">\n<style>{style}</style>\n{body}<script>{script}</script>\n')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(transform((ROOT / "phone_app" / "index.html").read_text()), encoding="utf-8")
    dst = out / "content"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(a.content, dst)
    files = sorted(str(p.relative_to(out)) for p in dst.rglob("*") if p.is_file())
    print(f"wrote {out / 'index.html'} and {len(files)} content files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
