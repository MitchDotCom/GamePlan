"""Go/no-go page from MLB clips: pitch data in, playable self-contained page out, answer keys from tracking (no hand labels).

  python -m gameplan.mlb_demo --game 777433 --work <dir> --out <dir>/gonogo_mlb.html --limit 8 [--pitcher NAME --stand L|R --top N]

Release here comes from the broadcast arrival sound minus plateTime (videocut.find_release).
Bottom 12% of the frame is cropped (scoreboard shows pitch type and speed after the pitch) and audio is removed.
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess
import time

from . import videocut as V
from .lowhome_demo import PAGE, LEAD, TAIL


def build(game: int, work: pathlib.Path, out_html: pathlib.Path, limit: int = 8, pitcher: str | None = None, seed: int = 1,
          stand: str | None = None, top: int = 0) -> list[dict]:
    feed = V.game_pitches(game)
    shapes = tuple(V.top_shapes(feed, pitcher, stand, top)) if top else ()
    if shapes:
        print("shapes for", pitcher, "vs", stand + "HH:", shapes)
    return build_rows(V.select(feed, pitcher=pitcher, limit=limit * 3, seed=seed, stand=stand, shapes=shapes), work, out_html, limit)


def build_rows(rows: list[dict], work: pathlib.Path, out_html: pathlib.Path, limit: int = 8, title: str | None = None) -> list[dict]:
    """Clips for these tracking rows (any games) into one page. Pitches with no clip or no clear release are skipped and printed."""
    work.mkdir(parents=True, exist_ok=True)
    items = []
    for p in rows:
        if len(items) >= limit:
            break
        url = V.clip_url(p["play_id"])
        if not url:
            continue
        src = work / f"{p['play_id']}.mp4"
        if not src.exists():
            V.download(url, src)
        rel = V.find_release(src, float(p["plateTime"]))
        time.sleep(0.3)
        if not rel:
            print(p["play_id"][:8], "skipped: no clear arrival sound")
            continue
        release = rel[0]
        cuts = V.scene_cuts(src)
        start = max(0.0, release - LEAD)
        early = [c for c in cuts if 0.2 < c < release - 0.4]
        if early:
            start = max(start, early[-1])
        later = [c for c in cuts if c > rel[1] - 0.05]
        end = min(release + TAIL, later[0] if later else release + TAIL)
        f = work / f"{p['play_id']}_page.mp4"
        subprocess.run([V._ffmpeg(), "-v", "error", "-y", "-i", str(src), "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-an", "-vf", "crop=iw:trunc(ih*0.88/2)*2:0:0",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(f)], check=True)
        k = V.answer_keys(p)
        info = f"{p.get('pitch_type')} {p.get('start_speed')} mph, {V.pocket(p)}, {p.get('description')}"
        items.append(dict(id=p["play_id"][:8], label=f"Pitch {len(items) + 1} ({p.get('pitcher_name')} to {p.get('batter_name')})", mime="video/mp4",
                          b64=base64.b64encode(f.read_bytes()).decode(), release=round(release - start, 4), release_frame=None,
                          zone_go=k["zone_go"], pitch_go=k["pitch_go"], result=info))
        print(items[-1]["label"], info, f"release {release:.3f} s (audio)")
    head = title or "Go / No-Go, MLB (center field view)"
    out_html.write_text(PAGE.replace("/*ITEMS*/[]", json.dumps(items)).replace("Go No-Go, Low Home", "Go No-Go, MLB").replace("Go / No-Go, low home", head), encoding="utf-8")
    return items


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=int, required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--pitcher", default=None)
    ap.add_argument("--stand", choices=["L", "R"], default=None, help="batter side")
    ap.add_argument("--top", type=int, default=0, help="use only the pitcher's N most-used (family, pocket) shapes vs this side; needs --pitcher and --stand")
    a = ap.parse_args(argv)
    build(a.game, pathlib.Path(a.work), pathlib.Path(a.out), a.limit, a.pitcher, stand=a.stand, top=a.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
