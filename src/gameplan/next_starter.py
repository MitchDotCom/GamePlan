"""Who is the opposing starter for our next game? Read from the MLB Stats API schedule, never guessed.

  python -m gameplan.next_starter --team 109 --on 2026-04-10

Finds the first game for `--team` that is not Final on or after `--on` (looking ahead up to 10 days) and reads the opponent's probable pitcher from the schedule.
Status is one of:
  confirmed   the opponent has a probable pitcher listed
  tbd         there is a game but no probable pitcher is listed yet (do not build; ask again later or pass the pitcher by hand)
  no_game     no unfinished game for this team in the window
A probable pitcher can change before first pitch, so the result carries `checked_at` and the caller should check again on game day.
"""
from __future__ import annotations

import argparse
import datetime
import json
import urllib.request

STATSAPI = "https://statsapi.mlb.com/api/v1"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _fetch(url: str) -> dict:
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read())


def resolve(team_id: int, on: str, days: int = 10, fetch=_fetch, now: datetime.datetime | None = None, sport_id: int = 1) -> dict:
    end = (datetime.date.fromisoformat(on) + datetime.timedelta(days=days)).isoformat()
    d = fetch(f"{STATSAPI}/schedule?sportId={sport_id}&teamId={team_id}&startDate={on}&endDate={end}&hydrate=probablePitcher,team")
    checked = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="minutes")
    games = sorted((g["gameDate"], dt["date"], g) for dt in d.get("dates", []) for g in dt["games"] if g["status"]["abstractGameState"] != "Final")
    if not games:
        return dict(status="no_game", team_id=team_id, on=on, checked_at=checked)
    _, date, g = games[0]
    ours = "home" if g["teams"]["home"]["team"]["id"] == team_id else "away"
    opp = g["teams"]["away" if ours == "home" else "home"]
    pp = opp.get("probablePitcher")
    out = dict(status="confirmed" if pp else "tbd", team_id=team_id, game_pk=g["gamePk"], date=date, game_time=g["gameDate"], we_are=ours,
               opponent=opp["team"].get("name"), opponent_id=opp["team"]["id"], season=int(g.get("season") or date[:4]), checked_at=checked)
    if pp:
        out.update(pitcher_id=pp["id"], pitcher_name=pp.get("fullName"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", type=int, required=True, help="MLB team id (for example 109 = Arizona)")
    ap.add_argument("--on", required=True, help="YYYY-MM-DD, the date to look from")
    a = ap.parse_args(argv)
    print(json.dumps(resolve(a.team, a.on), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
