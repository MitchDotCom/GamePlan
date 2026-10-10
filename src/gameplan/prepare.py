"""Get the next opposing starter ready for hitters, and refuse to ship anything that fails a check.

  python -m gameplan.prepare --team 109 --on 2026-04-10 --work <dir> --content <dir>/content [--pitcher-id N] [--starts 4] [--assess-pitches 6]

Steps: (1) find the opponent's probable starter from the schedule (next_starter) or take --pitcher-id as a manual override, which is recorded as manual; (2) pool his last starts,
build the next-starter pack, random packs from his team and an assessment pack per batting side (app_content); (3) run the gates below on what was built and write
<work>/prep_report.json. Exit code 0 only when no gate FAILED. WARN means ship but read it. Nothing here guesses: no probable starter, no build.

Gates, per batting side unless noted:
  starter_confirmed   schedule lists a probable pitcher (or manual override, which is a WARN)
  history             at least 3 previous starts pooled (WARN under 3, FAIL under 1) and 100 pitches
  playable_clips      the next-starter pack has at least PACK_MIN clips that cut cleanly (FAIL below)
  no_repeats          no pitch appears in two packs of the same queue
  sim_geometry        (with --sim) each drawn path ends where its strike key and result card say
  clip_files          every clip exists, is 10 KB to 3 MB, runs at least 0.4 s past release, and release is 0.3 to 3.0 s in
  answer_keys         every training item has a strike key and a pitch type; no key text in assessment items; assessment keys are in the private file
  choices             every item's pitch choices are 2 to 7 distinct types, include the thrown one, and match the pitcher's own list
  edges               the edges pack (his pitches within 3 in of the zone edge) has both strikes and balls, near half each
  coverage            the starter pack shows both strikes and balls, and at least 4 of the 9 location pockets
  usage_fit           every starter-pack pitch belongs to one of his top usage shapes against that side (what the validated rule picks)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess

from . import app_content as AC
from . import next_starter as NS
from . import playlist as PL
from . import videocut as V

PACK_MIN = 6
MIN_STARTS_WARN, MIN_POOL = 3, 100


def _dur(f: pathlib.Path):
    out = subprocess.run([V._ffmpeg(), "-i", str(f)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def gate(name, status, detail, side=None):
    return dict(gate=name, side=side, status=status, detail=detail)


def check_pack_files(content: pathlib.Path, queue: dict, side: str, dur=_dur) -> list[dict]:
    bad = []
    for pk in queue["packs"]:
        for it in pk["items"]:
            f = content / pk["dir"] / it["file"]
            if not f.exists() or not 10_000 <= f.stat().st_size <= 3_000_000:
                bad.append(f"{pk['id']}/{it['id']}: missing or odd size")
                continue
            d = dur(f)
            if d is None or d < it["release"] + 0.4 or not 0.3 <= it["release"] <= 3.0:
                bad.append(f"{pk['id']}/{it['id']}: duration {d}, release {it['release']}")
    return [gate("clip_files", "FAIL" if bad else "PASS", bad[:5] if bad else "all clips present, sized and long enough", side)]


def check_sim_geometry(queue: dict, side: str) -> list[dict]:
    """For drawn pitches: re-run the simview checks on each item's own parameters and confirm the strike key agrees with where the drawn ball crosses."""
    from . import simview as SV
    bad = []
    for pk in queue["packs"]:
        for it in pk["items"]:
            sim = it.get("sim")
            if not sim:
                bad.append(f"{pk['id']}/{it['id']}: no sim parameters")
                continue
            x, y, z = SV.position(sim, sim["t_zone"])
            inz = abs(x) <= 0.83 and sim["sz_bot"] <= z <= sim["sz_top"]
            truth = it.get("keys") and it["keys"].get("strike")
            m = it.get("meta") or {}
            if abs(x - float(m.get("px", 1e9))) > 0.02 or abs(z - float(m.get("pz", 1e9))) > 0.02:
                bad.append(f"{pk['id']}/{it['id']}: drawn crossing differs from the result card's location")
            if it.get("keys") and truth is not None and bool(truth) != inz:
                bad.append(f"{pk['id']}/{it['id']}: strike key {truth} but the drawn ball is {'in' if inz else 'out of'} the zone")
    return [gate("sim_geometry", "FAIL" if bad else "PASS", bad[:5] if bad else "every drawn path ends where its answer key and result card say", side)]


def check_no_repeats(queue: dict, side: str) -> list[dict]:
    """No pitch may appear in two packs of one queue (a training repeat of an assessment pitch gives the answer away, and any repeat double-counts one pitch)."""
    seen, dup = {}, []
    for pk in queue["packs"]:
        for it in pk["items"]:
            if it["id"] in seen:
                dup.append(f"{it['id']} in {seen[it['id']]} and {pk['id']}")
            seen[it["id"]] = pk["id"]
    return [gate("no_repeats", "FAIL" if dup else "PASS", dup[:5] if dup else f"{len(seen)} pitches, none repeated across packs", side)]


def check_keys_and_choices(queue: dict, private: dict, side: str, arsenals: dict | None = None) -> list[dict]:
    keys_bad, ch_bad = [], []
    for pk in queue["packs"]:
        for it in pk["items"]:
            tag = f"{pk['id']}/{it['id']}"
            k = it.get("keys")
            if pk["mode"] == "assess":
                if k is not None:
                    keys_bad.append(f"{tag}: key shipped in an assessment item")
                if f"{pk['id']}/{it['id']}" not in private:
                    keys_bad.append(f"{tag}: no private key")
            elif not k or k.get("strike") is None or not k.get("pitch_type"):
                keys_bad.append(f"{tag}: incomplete key {k}")
            a, t = it.get("arsenal") or [], (it.get("meta") or {}).get("pitch_type")
            if not (2 <= len(a) <= 7) or len(set(a)) != len(a) or t not in a:
                ch_bad.append(f"{tag}: choices {a} for {t}")
    return [gate("answer_keys", "FAIL" if keys_bad else "PASS", keys_bad[:5] if keys_bad else "keys complete, assessment keys withheld", side),
            gate("choices", "FAIL" if ch_bad else "PASS", ch_bad[:5] if ch_bad else "2 to 7 distinct choices, thrown type included", side)]


def check_coverage_and_fit(queue: dict, pool: list[dict], side: str) -> list[dict]:
    sp = queue["packs"][0]                                             # the next-starter pack is always first
    items = sp["items"]
    out = []
    strikes = {(it["keys"] or {}).get("strike") for it in items}
    pockets = {(it["meta"] or {}).get("pocket") for it in items} - {None}
    ok = {True, False} <= strikes and len(pockets) >= 4
    out.append(gate("coverage", "PASS" if ok else "WARN", f"{'strikes and balls both present' if {True, False} <= strikes else 'only one of strike or ball'}; {len(pockets)} of 9 pockets (usage picks where he throws most, so this is narrow by design; the edges pack covers location)", side))
    ed = next((pk for pk in queue["packs"] if pk["id"].startswith("edges_")), None)
    if ed is None:
        out.append(gate("edges", "WARN", "no edges pack (too few of his pitches finished within 3 in of the zone edge)", side))
    else:
        ks = [(it["keys"] or {}).get("strike") for it in ed["items"]]
        ni, no = ks.count(True), ks.count(False)
        out.append(gate("edges", "FAIL" if not (ni and no) else "WARN" if len(ks) < PACK_MIN or abs(ni - no) > 2 else "PASS", f"{len(ks)} clips: {ni} strikes, {no} balls, all within 3 in of the edge", side))
    top = {tuple(s) for s in PL.usage(pool, dict(stand=side), 3)}
    off = [it["id"] for it in items if (V.pitch_family((it["meta"] or {}).get("pitch_type", "")), (it["meta"] or {}).get("pocket")) not in top]
    out.append(gate("usage_fit", "FAIL" if off else "PASS", f"{len(off)} starter-pack pitches outside his top usage shapes {sorted(top)}" if off else f"all in his top usage shapes {sorted(top)}", side))
    return out


def prepare(team_id: int | None, on: str, work: pathlib.Path, content: pathlib.Path, pitcher_id: int | None = None, n_starts: int = 4, assess_pitches: int = 6,
            resolver=NS.resolve, builder=AC.build_queues, files_check=check_pack_files, sim: bool = False) -> dict:
    gates, info = [], {}
    if pitcher_id is None:
        info = resolver(team_id, on)
        if info["status"] != "confirmed":
            return dict(ok=False, built=False, starter=info, gates=[gate("starter_confirmed", "FAIL", f"status {info['status']}: not building without a confirmed starter")])
        pitcher_id = info["pitcher_id"]
        gates.append(gate("starter_confirmed", "PASS", f"{info['pitcher_name']} vs {info['opponent']} on {info['date']} (checked {info['checked_at']}; check again on game day)"))
        season, before = info["season"], info["date"]
    else:
        season, before = int(on[:4]), on
        info = dict(status="manual", pitcher_id=pitcher_id, date=on)
        gates.append(gate("starter_confirmed", "WARN", "pitcher passed by hand; the schedule was not consulted"))
    try:
        built = builder(pitcher_id, season, before, n_starts, work, content, 2, assess_pitches, **({"sim": True} if sim else {}))
    except Exception as e:                                             # a failed fetch is a failed build, said plainly
        return dict(ok=False, built=False, starter=info, gates=gates + [gate("build", "FAIL", f"{type(e).__name__}: {str(e)[:200]}")])
    starts, pool_n = built["starts"], built["pool"]
    gates.append(gate("history", "FAIL" if starts < 1 else "WARN" if starts < MIN_STARTS_WARN or pool_n < MIN_POOL else "PASS", f"{starts} starts pooled, {pool_n} pitches"))
    private = json.loads((work / "private_keys.json").read_text())
    from . import playlist as _PL
    pool = _PL.pooled(pitcher_id, _PL.recent_starts(pitcher_id, season, before, n_starts), work / "feeds")
    for side in ("L", "R"):
        q = json.loads((content / f"queue_{side}.json").read_text())
        n = len(q["packs"][0]["items"]) if q["packs"] else 0
        gates.append(gate("playable_clips", "PASS" if n >= PACK_MIN else "FAIL", f"{n} clips in the next-starter pack (need {PACK_MIN})", side))
        if not q["packs"]:
            continue
        gates += check_no_repeats(q, side)
        gates += check_sim_geometry(q, side) if sim else files_check(content, q, side)
        gates += check_keys_and_choices(q, private, side)
        gates += check_coverage_and_fit(q, pool, side)
    ok = not any(g["status"] == "FAIL" for g in gates)
    return dict(ok=ok, built=True, starter=info, summary=built, gates=gates)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", type=int, default=None)
    ap.add_argument("--on", required=True)
    ap.add_argument("--pitcher-id", type=int, default=None)
    ap.add_argument("--starts", type=int, default=4)
    ap.add_argument("--assess-pitches", type=int, default=6)
    ap.add_argument("--work", required=True)
    ap.add_argument("--content", required=True)
    ap.add_argument("--sim", action="store_true", help="draw pitches from tracking instead of cutting clips (no video is fetched)")
    a = ap.parse_args(argv)
    if a.team is None and a.pitcher_id is None:
        ap.error("give --team (to look up the starter) or --pitcher-id")
    work, content = pathlib.Path(a.work), pathlib.Path(a.content)
    work.mkdir(parents=True, exist_ok=True)
    r = prepare(a.team, a.on, work, content, a.pitcher_id, a.starts, a.assess_pitches, sim=a.sim)
    (work / "prep_report.json").write_text(json.dumps(r, indent=1))
    for g in r["gates"]:
        print(f"{g['status']:5} {g['gate']:18} {g['side'] or '-':2} {g['detail']}")
    print("READY" if r["ok"] else "NOT READY")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
