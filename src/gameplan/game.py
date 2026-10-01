"""Full-game viewer data: every plate appearance of one real game, both teams, nine innings.

For each side, the opposing starter's plan (pregame board for every batter who faced him, every count and time through the
order) and, pitch by pitch, the plan in force when each pitch was thrown, what the hitter did, and how the decision scored.
Plate appearances against relievers are shown with their results but have no plan (the engine is starters-only).
Everything is fit only on games before the game date, from public Savant data.

    python -m gameplan.game --league data/league --date 2025-08-19 --game 776685 --away HOU --home DET --out docs/gameview
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
from collections import Counter

from .decision import SituationPolicy
from .mockup import (Engine, _deltas, _encode_cells, _flip, build_board, load_events, load_pitcher_rows, pitcher_name,
                     swing_profile)
from .matchup import CELL_IN, X_RANGE, Z_RANGE, review_pitch
from .models import Action, Pitch, Result, Swing
from .path_variants import cell_region
from .savant import parse_swings

STEP = CELL_IN / 12.0
DESC = {"ball": "ball", "blocked_ball": "ball in the dirt", "called_strike": "called strike", "swinging_strike": "swinging strike",
        "swinging_strike_blocked": "swinging strike", "foul": "foul", "foul_tip": "foul tip", "hit_into_play": "in play",
        "hit_by_pitch": "hit by pitch", "foul_bunt": "foul bunt", "missed_bunt": "missed bunt", "pitchout": "pitchout",
        "automatic_ball": "automatic ball", "automatic_strike": "automatic strike", "bunt_foul_tip": "foul bunt"}
EVENT = {"strikeout": "Strikeout", "walk": "Walk", "single": "Single", "double": "Double", "triple": "Triple",
         "home_run": "Home run", "field_out": "Out in play", "force_out": "Force out", "grounded_into_double_play": "Double play",
         "double_play": "Double play", "hit_by_pitch": "Hit by pitch", "sac_fly": "Sacrifice fly", "sac_bunt": "Sacrifice bunt",
         "field_error": "Reached on error", "fielders_choice": "Fielder's choice", "fielders_choice_out": "Fielder's choice",
         "strikeout_double_play": "Strikeout, double play", "intent_walk": "Intentional walk", "catcher_interf": "Catcher interference",
         "sac_fly_double_play": "Sac fly, double play", "triple_play": "Triple play"}
RESULT_KIND = {"Strikeout": "k", "Walk": "bb", "Intentional walk": "bb", "Hit by pitch": "bb", "Single": "hit", "Double": "hit",
               "Triple": "hit", "Home run": "hit"}


def _int(v, d=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def load_game(league_dir: str, date: str, game_pk: str):
    rows = [r for r in csv.DictReader(open(pathlib.Path(league_dir) / f"{date}.csv", encoding="utf-8-sig")) if r["game_pk"] == game_pk]
    rows.sort(key=lambda r: (_int(r["at_bat_number"]), _int(r["pitch_number"])))
    return rows


def _bases(r) -> tuple:
    return tuple(bool(r.get(k)) for k in ("on_1b", "on_2b", "on_3b"))


def _bases_text(b) -> str:
    return "empty" if not any(b) else "-".join(n for n, on in zip(("1B", "2B", "3B"), b) if on)


def build_game(league_dir: str, date: str, game_pk: str, away: str, home: str, cache_dir: str) -> dict:
    rows = load_game(league_dir, date, game_pk)
    game_text = open(pathlib.Path(league_dir) / f"{date}.csv", encoding="utf-8-sig").read()
    sw_by_key = {(s.at_bat, s.pitch_no): s for s in parse_swings(game_text, include_takes=True) if s.game_pk == game_pk}
    events = load_events(league_dir, date)
    base = Engine(events, [], date, "0")
    pcache = str(pathlib.Path(cache_dir) / "pitcher_names_2025.csv")
    names = {r["batter"]: _flip(r.get("player_name", "")) for r in rows}
    pnames: dict[str, str] = {}
    pname = lambda p: pnames.setdefault(p, pitcher_name(pcache, p))

    team = {"Top": away, "Bot": home}
    fielding = {"Top": home, "Bot": away}
    starters = {}                       # half -> starter of the FIELDING team
    for half in ("Top", "Bot"):
        first = next(r for r in rows if r["inning_topbot"] == half)
        starters[half] = first["pitcher"]

    pas, pa_index = [], {}
    for r in rows:
        k = _int(r["at_bat_number"])
        if k not in pa_index:
            pa_index[k] = {"id": k, "inning": _int(r["inning"]), "half": r["inning_topbot"], "batter": r["batter"],
                           "pitcher": r["pitcher"], "pitches_raw": []}
            pas.append(pa_index[k])
        pa_index[k]["pitches_raw"].append(r)

    sides = {}
    for half in ("Top", "Bot"):
        starter = starters[half]
        faced = []
        for pa in pas:
            if pa["half"] == half and pa["pitcher"] == starter and pa["batter"] not in faced:
                faced.append(pa["batter"])
        eng = base.retarget(load_pitcher_rows(league_dir, starter, date), starter)
        stands = {}
        for h in faced:
            st = [s.stand for s in sw_by_key.values() if s.batter == h and s.stand]
            stands[h] = Counter(st).most_common(1)[0][0] if st else "R"
        print(f"{half}: {team[half]} batting vs {pname(starter)}; {len(faced)} hitters faced the starter", flush=True)
        board = build_board(eng, faced, names, stands, pname(starter))
        sides[half] = {"batting": team[half], "fielding": fielding[half], "starter": starter, "starter_name": pname(starter),
                       "board": board, "engine": eng, "stands": stands}

    out_pas = []
    for pa in pas:
        half = pa["half"]
        side = sides[half]
        eng, starter = side["engine"], side["starter"]
        h = pa["batter"]
        is_starter = pa["pitcher"] == starter
        hit = eng.hitter(h, names.get(h, ""))
        stand = side["stands"].get(h) or (Counter(s.stand for s in sw_by_key.values() if s.batter == h).most_common(1) or [("R", 0)])[0][0]
        pitches, dv_total, n_bad = [], 0.0, 0
        for r in pa["pitches_raw"]:
            b, s = _int(r["balls"]), _int(r["strikes"])
            outs, bases = _int(r["outs_when_up"]), _bases(r)
            lead = _int(r["bat_score"]) - _int(r["fld_score"])
            tto = min(max(_int(r["n_thruorder_pitcher"], 1), 1), 3)
            sw = sw_by_key.get((pa["id"], _int(r["pitch_number"])))
            rec = {"n": _int(r["pitch_number"]), "count": f"{b}-{s}", "outs": outs, "bases": _bases_text(bases), "lead": lead,
                   "type": r["pitch_type"], "velo": float(r["release_speed"]) if r["release_speed"] else None,
                   "desc": DESC.get(r["description"], r["description"]), "plan": None}
            if sw is not None and sw.x_away is not None:
                rec["x"], rec["z"] = round(sw.x_away, 2), round(sw.z, 2)
                i, j = int((sw.x_away - X_RANGE[0]) // STEP), int((sw.z - Z_RANGE[0]) // STEP)
                rec["region"] = cell_region(i, j) if 0 <= i < 5 and 0 <= j < 6 else "off the grid"
                rec["swing"] = bool(sw.swing)
                if is_starter and None not in (sw.velo, sw.ivb, sw.vaa):
                    call = "SWINGING_STRIKE" if (sw.swing and sw.whiff) else ("IN_PLAY" if sw.swing and (sw.xwoba is not None or sw.woba is not None)
                                                                               else "FOUL" if sw.swing else
                                                                               {"strike": "CALLED_STRIKE", "ball": "BALL", "hbp": "HBP"}.get(sw.take_call, "BALL"))
                    in_zone = abs(sw.x_away) <= 0.83 and (sw.sz_bot or 1.5) <= sw.z <= (sw.sz_top or 3.5)
                    res = Result(call, xwoba=sw.xwoba, in_zone=in_zone, is_hit=(sw.woba is not None and sw.woba >= 0.8))
                    pitch = Pitch(f"{game_pk}-{pa['id']}-{rec['n']}", sw.pitch_type, sw.x_away, sw.z, sw.velo, sw.ivb, sw.vaa)
                    swing = Swing(sw.attack_angle, sw.bat_speed, sw.squared_up) if sw.swing else None
                    plans = {}
                    for pol in (SituationPolicy.OFF, SituationPolicy.CONTACT_FIRST):
                        snap = eng.snapshot(h, tto, min(b, 3), min(s, 2), stand, hit, outs, bases, pol)
                        rv = review_pitch(snap, hit, pitch, Action.SWING if sw.swing else Action.TAKE, res, swing)
                        ev = rv.evaluation
                        plans[pol.value] = {"call": ev.instruction.value, "process": ev.process, "label": rv.label.value,
                                            "dv": None if ev.decision_value_runs is None else round(ev.decision_value_runs, 3),
                                            "flags": list(ev.flags), "delta": None if rv.model_delta is None else round(rv.model_delta, 3)}
                        if pol is SituationPolicy.OFF:
                            base_snap = snap
                    spot = bool(bases[2]) and outs < 2
                    if not spot:
                        plans["CONTACT_FIRST"] = plans["OFF"]
                    p0 = plans["OFF"]
                    if p0["dv"] is not None:
                        dv_total += p0["dv"]
                        n_bad += p0["process"] == "BAD"
                    rec["plan"] = {"policy": plans, "spot": spot, "tto": tto,
                                   "grid": _encode_cells(base_snap, base_snap.cells).get(sw.pitch_type),
                                   "deltas": _deltas(base_snap).get(sw.pitch_type)}
            pitches.append(rec)
        last = pa["pitches_raw"][-1]
        ev_text = EVENT.get(last.get("events", ""), last.get("events", "").replace("_", " ").capitalize() if last.get("events") else "")
        first = pa["pitches_raw"][0]
        out_pas.append({"id": pa["id"], "inning": pa["inning"], "half": half, "team": team[half], "batter": h,
                        "batter_name": names.get(h, h), "pitcher": pa["pitcher"], "pitcher_name": pname(pa["pitcher"]),
                        "vs_starter": is_starter, "result": ev_text or "In progress", "kind": RESULT_KIND.get(ev_text, "out"),
                        "outs": _int(first["outs_when_up"]), "bases": _bases_text(_bases(first)),
                        "lead": _int(first["bat_score"]) - _int(first["fld_score"]), "stand": stand,
                        "dv": round(dv_total, 2) if is_starter else None, "bad": n_bad if is_starter else None, "pitches": pitches})
    return {"date": date, "game_pk": game_pk, "away": away, "home": home,
            "sides": {half: {k: v for k, v in sd.items() if k not in ("engine", "stands")} for half, sd in sides.items()},
            "pas": out_pas,
            "swing_profiles": {p["batter"]: swing_profile(sides[p["half"]]["engine"], p["batter"]) for p in out_pas}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--game", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--out", default="docs/gameview")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    g = build_game(a.league, a.date, a.game, a.away, a.home, str(pathlib.Path(a.league).parent))
    (out / "game.json").write_text(json.dumps(g, separators=(",", ":")), encoding="utf-8")
    from .game_html import render
    (out / "game.html").write_text(render(g), encoding="utf-8")
    print(f"wrote {out / 'game.json'} ({len(g['pas'])} plate appearances) and {out / 'game.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
