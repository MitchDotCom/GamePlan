"""Build the phone app's content: packs of small clips plus queue_L.json and queue_R.json (what to show a left-handed or right-handed batter).

  python -m gameplan.app_content --pitcher-id 663903 --season 2025 --before 2025-06-11 --starts 4 --work <dir> --content <dir>/content [--random-packs 2] [--assess-pitches 12]

Per batting side the queue is: (1) the NEXT STARTER pack, his most-used shapes to that side from recent starts pooled (the validated usage rule), (2) RANDOM packs, other pitchers from the
starter's team in those same games, and optionally (3) an ASSESSMENT pack, a fixed set shown with no feedback whose answer keys are NOT shipped to the phone (written to
<work>/private_keys.json and applied on the server). Clips are small (640 px wide, no audio, bottom 12% cropped so the scoreboard cannot give the answer away).
MLB source: Savant game feed and clips (as in mlb_demo). The Visalia source is the TrackMan + low-home path in gameplan.visalia; its rows go through the same build_pack.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import random
import subprocess
import time

from . import playlist as PL
from . import videocut as V

LEAD, TAIL = 1.6, 2.0
PAUSE_MS = 100


def cut_clip(p: dict, work: pathlib.Path, out: pathlib.Path, scale_w: int = 640):
    """One pitch -> one small mp4 and its release time inside the clip, or None (no clip link or no clear release; never guessed)."""
    url = V.clip_url(p["play_id"])
    if not url:
        return None
    src = work / f"{p['play_id']}.mp4"
    if not src.exists():
        V.download(url, src)
    time.sleep(0.3)
    rel = V.find_release(src, float(p["plateTime"]))
    if not rel:
        return None
    release, arrival = rel[0], rel[1]
    cuts = V.scene_cuts(src)
    start = max(0.0, release - LEAD)
    early = [c for c in cuts if 0.2 < c < release - 0.4]
    if early:
        start = max(start, early[-1])
    later = [c for c in cuts if c > arrival - 0.05]
    end = min(release + TAIL, later[0] if later else release + TAIL)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([V._ffmpeg(), "-v", "error", "-y", "-i", str(src), "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-an",
                    "-vf", f"crop=iw:trunc(ih*0.88/2)*2:0:0,scale={scale_w}:-2", "-c:v", "libx264", "-profile:v", "main", "-preset", "veryfast", "-crf", "28",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)
    return dict(release=round(release - start, 4))


ARSENAL_MIN_SHARE, ARSENAL_MIN_N = 0.03, 5


def arsenals(rows: list[dict]) -> dict:
    """{pitcher id: pitch types he throws, most used first}. A type counts when it is at least 3% of his pitches and at least 5 of them, so a one-off does not become a choice."""
    from collections import Counter
    by = {}
    for p in rows:
        if p.get("type") == "pitch" and p.get("pitcher") is not None and p.get("pitch_type"):
            by.setdefault(p["pitcher"], Counter())[p["pitch_type"]] += 1
    return {k: [t for t, n in c.most_common() if n >= ARSENAL_MIN_N and n / sum(c.values()) >= ARSENAL_MIN_SHARE] for k, c in by.items()}


def build_pack(pid: str, title: str, subtitle: str, rows: list[dict], content: pathlib.Path, work: pathlib.Path, mode: str = "train", limit: int = 8, cutter=cut_clip,
               arsenal: dict | None = None, camera: str = "broadcast") -> tuple:
    """-> (pack dict for the queue, {item id: keys} for the private file). In an assessment pack the keys are withheld from the pack.
    Keys: strike (True when the ball crossed the zone by tracking, not the umpire's call) and pitch_type (what was thrown).
    Each item carries `camera` (what angle the clip was shot from: "broadcast" for MLB clips, "low_home" for Visalia footage) so results are never compared across angles.
    Each item carries `arsenal`, that pitcher's own pitch types, which are the choices for the second question. A pitch whose type is not in his arsenal list is skipped, never added to the choices."""
    items, private = [], {}
    for p in rows:
        if len(items) >= limit:
            break
        iid = p["play_id"][:12]
        opts = list((arsenal or {}).get(p.get("pitcher"), []))
        if arsenal is not None and (p.get("pitch_type") not in opts or len(opts) < 2):
            continue          # a rare pitch outside his arsenal list would stand out as the only odd choice, and a pitcher with one pitch type makes "which pitch" a question with one answer: neither is asked
        if arsenal is None:
            opts = [p["pitch_type"]] if p.get("pitch_type") else []
        r = cutter(p, work, content / pid / f"{iid}.mp4")
        if not r:
            continue
        k = V.answer_keys(p)
        keys = dict(strike=k["zone_go"], pitch_type=p.get("pitch_type"))
        private[iid] = keys
        items.append(dict(id=iid, file=None if r.get("sim") else f"{iid}.mp4", release=r["release"], sim=r.get("sim"), keys=keys if mode == "train" else None, arsenal=opts,
                          camera="sim" if r.get("sim") else camera, meta=V.pitch_meta(p),
                          label=f"Pitch {len(items) + 1}", result=None))
    return dict(id=pid, dir=pid, title=title, subtitle=subtitle, mode=mode, items=items), private


def team_pool(feeds: pathlib.Path, team_id, exclude_pitcher) -> list[dict]:
    out = []
    for f in sorted(feeds.glob("*.json")):
        for p in json.loads(f.read_text()):
            if (p.get("type") == "pitch" and p.get("team_fielding_id") == team_id and p.get("pitcher") != exclude_pitcher and p.get("play_id") and p.get("plateTime")
                    and p.get("px") is not None and p.get("pfxX") is not None):
                out.append(dict(p, game_pk=str(p.get("game_pk") or f.stem)))
    return out


EDGE_FT = 0.25          # 3 inches


def fresh(rows: list[dict], used: set) -> list[dict]:
    """Rows whose pitch is not already in some pack of this queue. No pitch may appear twice for a hitter: a training repeat of an assessment pitch hands him the answer."""
    return [r for r in rows if r.get("play_id", "")[:12] not in used]


def edge_rows(pool: list[dict], side: str, rnd: random.Random, exclude: set | None = None) -> list[dict]:
    """His pitches to this side that finished within 3 inches of the zone edge, alternating inside and outside so strike or ball is a real question, in a fixed-seed order.
    Pitches whose clip id is in `exclude` (the next-starter pack's) are left out so no hitter sees the same pitch twice in one queue.
    Extra rows are returned beyond the pack size because some clips will not cut cleanly (build_pack stops at its limit)."""
    ins, outs = [], []
    for p in pool:
        d = V.edge_ft(p)
        if p.get("stand") == side and d is not None and abs(d) < EDGE_FT and p.get("play_id") and p.get("plateTime") and p["play_id"][:12] not in (exclude or set()):
            (ins if d < 0 else outs).append(p)
    rnd.shuffle(ins)
    rnd.shuffle(outs)
    mixed = []
    for i in range(max(len(ins), len(outs))):
        mixed += ins[i:i + 1] + outs[i:i + 1]
    return mixed


def build_queues(pitcher_id: int, season: int, before: str, n_starts: int, work: pathlib.Path, content: pathlib.Path, n_random: int = 2, assess_pitches: int = 0,
                 seed: str | None = None, per_pack: int = 8, cutter=cut_clip, sim: bool = False) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    content.mkdir(parents=True, exist_ok=True)
    if sim:                                         # drawn from tracking: no clip is fetched, cut or stored
        from . import simview
        cutter = simview.sim_cutter
    starts = PL.recent_starts(pitcher_id, season, before, n_starts)
    pool = PL.pooled(pitcher_id, starts, work / "feeds")
    if not pool:
        raise ValueError("no pitches for this starter before that date")
    name, team = pool[0].get("pitcher_name"), pool[0].get("team_fielding_id")
    mates = team_pool(work / "feeds", team, pitcher_id)
    rnd = random.Random(seed or before)
    ars = arsenals(pool + mates)
    private, queues = {}, {}
    for side in ("L", "R"):
        hit = dict(stand=side, name=side)
        pl = PL.playlist("usage", pool, hit, 3, 10 ** 6)
        packs = []
        sp, pk = build_pack(f"starter_{pitcher_id}_{side}", f"Next starter: {name}", f"Vs {'left' if side == 'L' else 'right'}-handed batters. His most-used pitches from his last {len(starts)} starts.",
                            pl["pitches"][: per_pack * 3], content, work, "train", per_pack, cutter, ars)
        packs.append(sp); private.update({f"{sp['id']}/{k}": v for k, v in pk.items()})
        used = {i["id"] for i in sp["items"]}
        ep, pk = build_pack(f"edges_{pitcher_id}_{side}", f"Edges: {name}", f"Vs {'left' if side == 'L' else 'right'}-handed batters. His pitches within 3 inches of the zone edge, half in and half out, from any spot.",
                            edge_rows(pool, side, random.Random(f"{seed or before}-edges-{side}"), {i["id"] for i in sp["items"]}), content, work, "train", per_pack, cutter, ars)
        if ep["items"]:
            packs.append(ep); private.update({f"{ep['id']}/{k}": v for k, v in pk.items()})
            used |= {i["id"] for i in ep["items"]}
        by_p = {}
        for p in mates:
            if p.get("stand") == side:
                by_p.setdefault(p["pitcher"], []).append(p)
        names = [k for k, v in by_p.items() if len(v) >= 12]
        rnd.shuffle(names)
        for i, pid_ in enumerate(names[:n_random]):
            rs = fresh(by_p[pid_], used)
            rnd.shuffle(rs)
            rp, pk = build_pack(f"random_{pid_}_{side}", f"Random: {rs[0].get('pitcher_name')}", f"{rs[0].get('team_fielding') or 'Same team'}, mixed pitches.", rs[: per_pack * 3], content, work, "train", per_pack, cutter, ars)
            packs.append(rp); private.update({f"{rp['id']}/{k}": v for k, v in pk.items()})
            used |= {i["id"] for i in rp["items"]}
        if assess_pitches:
            allr = fresh([p for p in mates + pool if p.get("stand") == side], used)
            rnd.shuffle(allr)
            ap, pk = build_pack(f"assess_{side}", "Assessment", "No feedback. Scored later.", allr[: assess_pitches * 3], content, work, "assess", assess_pitches, cutter, ars)
            packs.append(ap); private.update({f"{ap['id']}/{k}": v for k, v in pk.items()})
        packs = [p for p in packs if p["items"]]
        q = dict(version=1, generated=datetime.datetime.now().isoformat(timespec="minutes"), side=side, pause_ms=PAUSE_MS, packs=packs)
        (content / f"queue_{side}.json").write_text(json.dumps(q))
        queues[side] = [(p["title"], len(p["items"])) for p in packs]
    (work / "private_keys.json").write_text(json.dumps(private))
    return dict(starts=len(starts), pool=len(pool), queues=queues)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitcher-id", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--before", required=True)
    ap.add_argument("--starts", type=int, default=5)
    ap.add_argument("--random-packs", type=int, default=2)
    ap.add_argument("--assess-pitches", type=int, default=0)
    ap.add_argument("--per-pack", type=int, default=8)
    ap.add_argument("--work", required=True)
    ap.add_argument("--content", required=True)
    a = ap.parse_args(argv)
    print(json.dumps(build_queues(a.pitcher_id, a.season, a.before, a.starts, pathlib.Path(a.work), pathlib.Path(a.content), a.random_packs, a.assess_pitches, per_pack=a.per_pack), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
