"""Triple-A and Florida State League stress test of the hitter-specific playlists, from cached public game feeds (gameplan.milb_feed).

Questions, each answered with numbers (docs/MILB_STRESS_TEST.md):
  1 coverage    how many hitters have enough swings for a ride list and a run list, over a full season and by a mid-season date?
  2 reliability is the slope stable within a hitter at this level? Same estimator and the same pre-registered bar as the MLB test (corrected split-half r >= 0.40, CI lower end > 0).
  3 lineup plan does the lineup command run end to end for a real starter from these feeds?

  python -m gameplan.milb_study --cache <dir> --label FSL --out <dir>
"""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import defaultdict

import numpy as np

from . import milb_feed as MF
from . import playlist as PL
from . import playlist_reliability as PR
from . import trackman as TM
from . import videocut as V

DESC = {"Swinging Strike": "swinging_strike", "Swinging Strike (Blocked)": "swinging_strike", "Foul Tip": "foul_tip", "Foul": "foul", "Foul Bunt": "foul_bunt",
        "Missed Bunt": "missed_bunt", "Called Strike": "called_strike", "Ball": "ball", "Ball In Dirt": "ball", "Pitchout": "ball"}


def desc(p: dict):
    d = p.get("description") or ""
    if d.startswith("In play"):
        return "hit_into_play"
    return DESC.get(d)


def by_hitter(pitches: list[dict]) -> dict:
    """{batter_id: Statcast-like rows trait_slope reads}. Rows without a mapped call or without movement are skipped (counted by the caller via length)."""
    out = defaultdict(list)
    for p in pitches:
        d = desc(p)
        ride, run = PL.starter_move(p)
        if not d or ride is None or p.get("stand") not in ("L", "R"):
            continue
        out[str(p["batter"])].append(dict(pitch_type=p["pitch_type"], description=d, pfx_z=ride / 12.0, api_break_x_batter_in=run / 12.0, plate_x=p["px"], plate_z=p["pz"],
                                          release_speed=p["start_speed"], strikes=str(p.get("strikes")), stand=p["stand"], p_throws=p["p_throws"], game_pk=p["game_pk"],
                                          _season=p["_season"], _date=p["_date"], batter_name=p.get("batter_name")))
    return out


def swings(rows: list[dict], fam: str) -> int:
    return sum(1 for r in rows if V.pitch_family(r["pitch_type"]) == fam and r["description"] in PL.savant.SWING_DESCRIPTIONS | {"foul_tip"})


def coverage(hist: dict, min_swings: int = PL.MIN_SWINGS, cutoff: str | None = None) -> dict:
    res = {}
    for trait, fam in (("ride", "FB"), ("run", "BRK")):
        n = []
        for rows in hist.values():
            rr = [r for r in rows if not cutoff or r["_date"] < cutoff]
            n.append(swings(rr, fam))
        n = np.array(n)
        res[trait] = dict(hitters=int(len(n)), with_min=int((n >= min_swings).sum()), share=round(float((n >= min_swings).mean()), 3), median_swings=int(np.median(n)))
    return res


def reliability(hist: dict, min_each: int = PR.MIN_EACH) -> dict:
    out = {}
    for trait, fam in (("ride", "FB"), ("run", "BRK")):
        odd, even = [], []
        for rows in hist.values():
            gp = sorted({r["game_pk"] for r in rows})
            par = {g: i % 2 for i, g in enumerate(gp)}
            a = PL.trait_slope([r for r in rows if par[r["game_pk"]] == 0], fam, trait, min_swings=min_each, boot=0)
            b = PL.trait_slope([r for r in rows if par[r["game_pk"]] == 1], fam, trait, min_swings=min_each, boot=0)
            if a["ok"] and b["ok"]:
                odd.append(a["slope"]); even.append(b["slope"])
        if len(odd) >= 8:
            r = float(np.corrcoef(odd, even)[0, 1])
            lo, hi = PR.boot_r(odd, even)
            out[trait] = dict(n=len(odd), r=round(r, 3), ci=[round(float(lo), 3), round(float(hi), 3)], corrected=round(PR.sb(r), 3),
                              passes_bar=bool(PR.sb(r) >= PR.BAR and lo > 0))
        else:
            out[trait] = dict(n=len(odd), r=None, passes_bar=False)
    return out


def year_over_year(prev: dict, cur: dict, min_swings: int = PR.MIN_EACH) -> dict:
    """Slope in the earlier season vs the later one, for hitters with at least min_swings swings in the family in both. Plain r with a hitter bootstrap interval."""
    out = {}
    for trait, fam in (("ride", "FB"), ("run", "BRK")):
        a, b = [], []
        for k in set(prev) & set(cur):
            x = PL.trait_slope(prev[k], fam, trait, min_swings=min_swings, boot=0)
            y = PL.trait_slope(cur[k], fam, trait, min_swings=min_swings, boot=0)
            if x["ok"] and y["ok"]:
                a.append(x["slope"]); b.append(y["slope"])
        if len(a) >= 8:
            lo, hi = PR.boot_r(a, b)
            out[trait] = dict(n=len(a), r=round(float(np.corrcoef(a, b)[0, 1]), 3), ci=[round(float(lo), 3), round(float(hi), 3)])
        else:
            out[trait] = dict(n=len(a), r=None)
    out["hitters_in_both_seasons"] = len(set(prev) & set(cur))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--midseason", default="2025-06-15")
    ap.add_argument("--prior-cache", default=None, help="the previous season's cache, for the year-over-year check")
    ap.add_argument("--min-pitches", type=int, default=300, help="hitters with fewer tracked rows than this are ignored")
    a = ap.parse_args(argv)
    pitches = MF.load(pathlib.Path(a.cache))
    hist = {k: v for k, v in by_hitter(pitches).items() if len(v) >= a.min_pitches}
    res = dict(label=a.label, tracked_pitches=len(pitches), hitters=len(hist), coverage_full=coverage(hist), coverage_midseason=coverage(hist, cutoff=a.midseason),
               reliability=reliability(hist))
    if a.prior_cache:
        prev = {k: v for k, v in by_hitter(MF.load(pathlib.Path(a.prior_cache))).items() if len(v) >= a.min_pitches}
        res["year_over_year"] = year_over_year(prev, hist)
        res["prior_hitters"] = len(prev)
    pathlib.Path(a.out, f"milb_study_{a.label}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
