"""Bulk Savant pulls: qualified batters and qualified starters for a season, trimmed to the columns
the models use so a full league pull stays small.

    python -m gameplan.bulk --season 2025 --batters data/b --pitchers data/p
"""
from __future__ import annotations

import argparse
import csv
import io
import pathlib
import time
import urllib.parse

from .savant import SEARCH_URL, fetch_csv

KEEP = [
    "pitch_type", "game_date", "game_pk", "at_bat_number", "pitch_number", "batter", "pitcher",
    "player_name", "stand", "p_throws", "description", "balls", "strikes", "inning",
    "inning_topbot", "n_thruorder_pitcher", "release_speed", "release_spin_rate", "release_extension",
    "release_pos_x", "release_pos_z", "arm_angle", "pfx_x", "pfx_z", "api_break_x_batter_in",
    "plate_x", "plate_z", "sz_top", "sz_bot", "vx0", "vy0", "vz0", "ax", "ay", "az",
    "launch_speed", "launch_angle", "estimated_woba_using_speedangle", "woba_value",
    "bat_speed", "swing_length", "attack_angle", "attack_direction", "swing_path_tilt",
    "pitcher_days_since_prev_game", "n_priorpa_thisgame_player_at_bat", "bat_score", "fld_score",
    "on_1b", "on_2b", "on_3b", "outs_when_up", "delta_run_exp", "events",
]


def leaderboard_ids(kind: str, season: int, minimum: str = "q") -> list[int]:
    """kind: 'batter' or 'pitcher'. minimum: 'q' (qualified) or an integer as a string."""
    sel = "player_age,pa" if kind == "batter" else "player_age,p_game"
    url = ("https://baseballsavant.mlb.com/leaderboard/custom?" + urllib.parse.urlencode({
        "year": season, "type": kind, "filter": "", "min": minimum, "selections": sel,
        "chart": "false", "x": "player_age", "y": "player_age", "r": "no",
        "chartType": "beeswarm", "csv": "true"}))
    rows = csv.DictReader(io.StringIO(fetch_csv(url)))
    return [int(r["player_id"]) for r in rows]


def player_url(kind: str, player_id: int, season: int) -> str:
    params = {
        "all": "true", "hfSea": f"{season}|", "hfGT": "R|", "player_type": kind,
        f"{kind}s_lookup[]": str(player_id), "min_pitches": "0", "min_results": "0",
        "group_by": "name", "sort_col": "pitches", "sort_order": "desc", "type": "details",
    }
    return SEARCH_URL + "?" + urllib.parse.urlencode(params)


def trim(csv_text: str) -> str:
    src = csv.DictReader(io.StringIO(csv_text))
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=KEEP, extrasaction="ignore")
    w.writeheader()
    for row in src:
        w.writerow(row)
    return out.getvalue()


def fetch_all(kind: str, ids: list[int], season: int, outdir: str, pause: float = 1.0) -> None:
    d = pathlib.Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    for i, pid in enumerate(ids, 1):
        path = d / f"{pid}_{season}.csv"
        if path.exists():
            continue
        for attempt in range(3):
            try:
                path.write_text(trim(fetch_csv(player_url(kind, pid, season))))
                print(f"[{i}/{len(ids)}] {kind} {pid} ok", flush=True)
                break
            except Exception as e:  # network hiccup or rate limit: back off and retry
                print(f"[{i}/{len(ids)}] {kind} {pid} attempt {attempt + 1} failed: {e}", flush=True)
                time.sleep(5 * (attempt + 1))
        time.sleep(pause)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--batters", help="output dir for qualified batters")
    ap.add_argument("--pitchers", help="output dir for qualified pitchers")
    ap.add_argument("--pitcher-min", default="q", help="leaderboard min for pitchers, e.g. q or 100")
    a = ap.parse_args(argv)
    if a.pitchers:
        fetch_all("pitcher", leaderboard_ids("pitcher", a.season, a.pitcher_min), a.season, a.pitchers)
    if a.batters:
        fetch_all("batter", leaderboard_ids("batter", a.season, "q"), a.season, a.batters)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
