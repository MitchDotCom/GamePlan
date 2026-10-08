"""Triple-A and Florida State League tracking from Savant's public game feed, via the Stats API schedule.

  python -m gameplan.milb_feed fetch --league FSL --start 2025-04-04 --end 2025-09-20 --cache <dir> [--workers 6]

What was verified (2026-10-08): the game feed (baseballsavant.mlb.com/gf) carries full pitch tracking for Triple-A (sportId 11) and Florida State League (sportId 14,
leagueId 123) games, and none for the Carolina and California League games checked. There are no clips for any of them (sporty-videos returned 0 of 32 links).
The minor-league CSV search could not be used: its level parameter is defined in a script on a host this environment's network policy blocks, and the unfiltered
search returned spring-training MLB rows for a Florida State League player, so it is not used here.

Games are cached one JSON file per game (pitches only, with tracking-coverage counted), so a run resumes and a re-run fetches only what is new.
Feeds with no tracking are kept as empty and counted, never silently dropped: fail closed on coverage, not on the whole run.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import videocut as V

STATSAPI = "https://statsapi.mlb.com/api/v1"
LEAGUES = {"FSL": (14, 123), "AAA-IL": (11, 117), "AAA-PCL": (11, 112)}
TRACK_KEYS = ("pitch_type", "start_speed", "px", "pz", "pfxX", "pfxZ")


def schedule(league: str, start: str, end: str) -> list[tuple]:
    sport, lg = LEAGUES[league]
    req = urllib.request.Request(f"{STATSAPI}/schedule?sportId={sport}&leagueId={lg}&startDate={start}&endDate={end}", headers={"User-Agent": V.UA})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return sorted((g["officialDate"], g["gamePk"]) for dt in d["dates"] for g in dt["games"] if g["status"]["abstractGameState"] == "Final")


def _tracked(p: dict) -> bool:
    return all(p.get(k) not in (None, "") for k in TRACK_KEYS)


def fetch_game(date: str, pk: int, cache: pathlib.Path) -> dict:
    f = cache / f"{pk}.json"
    if f.exists():
        try:
            return json.loads(f.read_text())["meta"]
        except (json.JSONDecodeError, KeyError):     # a run killed mid-write leaves a partial file; refetch it
            f.unlink()
    for attempt in range(3):
        try:
            ps = [p for p in V.game_pitches(pk) if p.get("type") == "pitch"]
            break
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(2 * (attempt + 1))
    else:
        return dict(game_pk=pk, date=date, error=err)
    keep = [p for p in ps if _tracked(p)]
    meta = dict(game_pk=pk, date=date, pitches=len(ps), tracked=len(keep), year=int(date[:4]))
    tmp = f.with_name(f"{f.stem}.{os.getpid()}.{threading.get_ident()}.tmp")   # unique per process and thread, so overlapping runs cannot collide
    tmp.write_text(json.dumps(dict(meta=meta, pitches=keep)))
    tmp.replace(f)                                   # atomic: a reader never sees half a file
    return meta


def fetch(league: str, start: str, end: str, cache: pathlib.Path, workers: int = 6) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    games = schedule(league, start, end)
    t = time.time()
    with ThreadPoolExecutor(workers) as ex:
        metas = list(ex.map(lambda g: fetch_game(g[0], g[1], cache), games))
    err = [m for m in metas if "error" in m]
    tot = sum(m.get("pitches", 0) for m in metas)
    trk = sum(m.get("tracked", 0) for m in metas)
    summary = dict(league=league, games=len(games), errors=len(err), pitches=tot, tracked=trk, tracked_share=round(trk / tot, 4) if tot else None,
                   games_with_no_tracking=sum(1 for m in metas if m.get("pitches") and not m.get("tracked")), seconds=round(time.time() - t))
    (cache / "_summary.json").write_text(json.dumps(summary))
    return summary


def load(cache: pathlib.Path, since: str | None = None, before: str | None = None) -> list[dict]:
    """Tracked pitches from every cached game, tagged with game date (_date), season (_season) and game_pk."""
    out = []
    for f in sorted(cache.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        m = d["meta"]
        if (since and m["date"] < since) or (before and m["date"] >= before):
            continue
        out += [dict(p, game_pk=str(m["game_pk"]), _date=m["date"], _season=m["year"]) for p in d["pitches"]]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--league", choices=sorted(LEAGUES), required=True)
    f.add_argument("--start", required=True)
    f.add_argument("--end", required=True)
    f.add_argument("--cache", required=True)
    f.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    print(json.dumps(fetch(a.league, a.start, a.end, pathlib.Path(a.cache), a.workers)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
