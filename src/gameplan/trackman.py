"""TrackMan export (standard column names) -> the row schema the playlists use. Built without a sample export; validated by converting MLB data into a
TrackMan-style table and checking the adapter recovers the MLB values (src/gameplan/trackman_validate.py).

Column names used (standard TrackMan CSV): Date, PitchNo, PitchUID, GameID, Pitcher, PitcherId, PitcherThrows, PitcherTeam, Batter, BatterId, BatterSide, BatterTeam,
Balls, Strikes, TaggedPitchType, PitchCall, RelSpeed, InducedVertBreak, HorzBreak, PlateLocHeight, PlateLocSide, ZoneTime (optional).
Missing required columns raise with the list of what is missing. Nothing is guessed:

  * Sign of PlateLocSide and HorzBreak is inferred from the data, not assumed, and the adapter refuses when the data cannot decide.
      plate side: pitchers throw more pitches away from a batter than in, so the batter side whose pitches average further toward + is the side that + points away from.
                  If right-handed batters average positive, + is toward first base (catcher's right), the Statcast convention the study uses.
      horizontal break: HorzBreak is x-signed. A right-handed pitcher's fastballs and sinkers run arm-side, toward first base, so their mean sign says which way
                  HorzBreak points. Left-handed pitchers' fastballs and sinkers must come out the opposite sign or the adapter refuses.
  * Strike-zone top and bottom are not in a TrackMan export. The pocket's height thirds use SZ_DEFAULT (1.5 to 3.5 ft) unless the caller passes per-batter heights.
  * There is no run expectancy in TrackMan, so the hitter-cost playlist is unavailable from TrackMan history. Ride, run and usage work.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict

import numpy as np

SZ_DEFAULT = (3.5, 1.5)     # (top, bottom) feet
REQUIRED = ("Date", "PitcherId", "PitcherThrows", "BatterId", "BatterSide", "Balls", "Strikes", "TaggedPitchType", "PitchCall", "RelSpeed",
            "InducedVertBreak", "HorzBreak", "PlateLocHeight", "PlateLocSide")

_NAME = {"fourseamfastball": "FF", "fastball": "FF", "fourseam": "FF", "ffastball": "FF", "twoseamfastball": "SI", "sinker": "SI", "cutter": "FC",
         "slider": "SL", "sweeper": "ST", "slurve": "SV", "curveball": "CU", "knucklecurve": "KC", "changeup": "CH", "splitter": "FS", "forkball": "FO", "knuckleball": "KN"}
_CALL = {"strikeswinging": "swinging_strike", "foulball": "foul", "foulballnotfieldable": "foul", "foulballfieldable": "foul", "inplay": "hit_into_play",
         "strikecalled": "called_strike", "ballcalled": "ball", "ballintheDirt".lower(): "ball", "hitbypitch": "hit_by_pitch"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def pitch_code(name: str):
    return _NAME.get(_norm(name))


def _side(v: str):
    v = _norm(v)
    return "R" if v.startswith("r") else "L" if v.startswith("l") else None


def _f(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def read(csv_text: str) -> list[dict]:
    rd = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    missing = [c for c in REQUIRED if c not in (rd.fieldnames or [])]
    if missing:
        raise ValueError(f"TrackMan export is missing columns: {missing}")
    return list(rd)


def infer_plate_sign(rows: list[dict], min_each: int = 200, margin: float = 0.05) -> int:
    """+1 if PlateLocSide is positive toward first base (right-handed batters average positive), -1 if opposite. Raises if the data cannot decide."""
    xs = {"R": [], "L": []}
    for r in rows:
        s, x = _side(r["BatterSide"]), _f(r["PlateLocSide"])
        if s and x is not None:
            xs[s].append(x)
    if min(len(xs["R"]), len(xs["L"])) < min_each:
        raise ValueError(f"cannot infer plate-side sign: {len(xs['R'])} pitches to RHB, {len(xs['L'])} to LHB (need {min_each} each)")
    gap = float(np.mean(xs["R"]) - np.mean(xs["L"]))
    if abs(gap) < margin:
        raise ValueError(f"cannot infer plate-side sign: RHB and LHB averages differ by only {gap:+.3f} ft")
    return 1 if gap > 0 else -1


def infer_arm_sign(rows: list[dict], min_each: int = 100, margin: float = 2.0) -> int:
    """Sign of HorzBreak (inches) for movement toward first base, from right-handed pitchers' fastballs and sinkers (arm-side = toward first base). Left-handed pitchers must come out opposite or it raises."""
    hb = {"R": [], "L": []}
    for r in rows:
        if pitch_code(r["TaggedPitchType"]) in ("FF", "SI"):
            h, x = _side(r["PitcherThrows"]), _f(r["HorzBreak"])
            if h and x is not None:
                hb[h].append(x)
    if min(len(hb["R"]), len(hb["L"])) < min_each:
        raise ValueError(f"cannot infer horizontal-break sign: {len(hb['R'])} RHP and {len(hb['L'])} LHP fastballs/sinkers (need {min_each} each)")
    mr, ml = float(np.mean(hb["R"])), float(np.mean(hb["L"]))
    if abs(mr) < margin or abs(ml) < margin or np.sign(mr) == np.sign(ml):
        raise ValueError(f"cannot infer horizontal-break sign: mean HorzBreak RHP {mr:+.1f} in, LHP {ml:+.1f} in")
    return int(np.sign(mr))


class Signs:
    def __init__(self, plate: int, arm: int):
        self.plate, self.arm = plate, arm


def infer_signs(rows: list[dict]) -> Signs:
    return Signs(infer_plate_sign(rows), infer_arm_sign(rows))


def convert(rows: list[dict], signs: Signs, sz: dict | None = None) -> list[dict]:
    """TrackMan rows -> feed-style pitch rows (keys the playlists read). `sz` maps BatterId -> (top, bottom) if you have it, else SZ_DEFAULT."""
    out = []
    for i, r in enumerate(rows):
        px, pz, ride, hb = _f(r["PlateLocSide"]), _f(r["PlateLocHeight"]), _f(r["InducedVertBreak"]), _f(r["HorzBreak"])
        stand, hand, code = _side(r["BatterSide"]), _side(r["PitcherThrows"]), pitch_code(r["TaggedPitchType"])
        if None in (px, pz, ride, hb) or not (stand and hand and code):
            continue
        toward_1b = hb * signs.arm                           # HorzBreak is x-signed, not hand-normalized; a RHP's arm-side is toward first base, which fixes the sign
        away = toward_1b * (1 if stand == "R" else -1)       # first base is away from a right-handed batter and toward a left-handed one (the study's column)
        top, bot = (sz or {}).get(r["BatterId"], SZ_DEFAULT)
        out.append(dict(type="pitch", play_id=r.get("PitchUID") or f"{r['Date']}-{r.get('PitchNo', i)}", plateTime=_f(r.get("ZoneTime")) or 0.0,
                        pitcher=r["PitcherId"], pitcher_name=r.get("Pitcher"), p_throws=hand, batter=r["BatterId"], batter_name=r.get("Batter"), stand=stand,
                        pitch_type=code, px=signs.plate * px, pz=pz, sz_top=top, sz_bot=bot, balls=int(float(r["Balls"])), strikes=int(float(r["Strikes"])),
                        start_speed=_f(r["RelSpeed"]), game_pk=r.get("GameID") or r["Date"], _date=r["Date"], _ride_in=ride, _run_in=away,
                        inning=r.get("Inning"), pa=r.get("PAofInning"), pitch_of_pa=r.get("PitchofPA"), pitch_call=r.get("PitchCall")))
    return out


def pool(pitches: list[dict], pitcher_id, n_starts: int, before: str) -> list[dict]:
    """Same shape as playlist.pooled: this pitcher's last n games before a date (a start = a game in which he threw), tagged with _age (0 = most recent)."""
    games = defaultdict(list)
    for p in pitches:
        if str(p["pitcher"]) == str(pitcher_id) and p["_date"] < before:
            games[(p["_date"], p["game_pk"])].append(p)
    keep = sorted(games, reverse=True)[:n_starts]
    return [dict(p, _age=age) for age, k in enumerate(keep) for p in games[k]]


def hitter_rows(rows: list[dict], signs: Signs, batter_id) -> list[dict]:
    """One batter's TrackMan rows as the Statcast-like rows trait_slope reads. No delta_run_exp (not in TrackMan), so hitter_cost cannot run from these."""
    out = []
    for r in rows:
        if str(r["BatterId"]) != str(batter_id):
            continue
        cv = convert([r], signs)
        call = _CALL.get(_norm(r["PitchCall"]))
        if not cv or not call:
            continue
        c = cv[0]
        out.append(dict(pitch_type=c["pitch_type"], description=call, pfx_z=c["_ride_in"] / 12.0, api_break_x_batter_in=c["_run_in"] / 12.0, plate_x=c["px"], plate_z=c["pz"],
                        sz_top=c["sz_top"], sz_bot=c["sz_bot"], release_speed=c["start_speed"], strikes=str(c["strikes"]), balls=str(c["balls"]), stand=c["stand"],
                        p_throws=c["p_throws"], game_pk=c["game_pk"], _season=int(r["Date"][:4])))
    return out
