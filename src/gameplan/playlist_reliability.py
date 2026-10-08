"""Is a hitter's ride / run slope a stable trait? Pre-registered 2026-10-08, before the first run.

Question: does the slope from one part of his history predict the slope from another part?
Hitters: those who appear in the game feeds of a set of MLB games (first N with at least MIN_EACH swings in the family in BOTH halves).
Estimator: playlist.trait_slope (ridge K=100, no bootstrap), the same one the playlists use.
Tests:
  split-half   odd vs even games within 2023 to 2025 (by game_pk rank), Spearman-Brown corrected r
  year-over-year  2024 slope vs 2025 slope, plain r
Bar (set before running): corrected split-half r at least 0.40 for a trait, with the lower end of a hitter-bootstrap 95% interval above 0.
A trait that misses stays out of hitter-specific playlists (playlist then uses usage for that hitter).
Hitters are chosen by game appearance, not by their slopes. Report every hitter count.

  python -m gameplan.playlist_reliability --games 777433,777435,... --seasons 2023,2024,2025 --work <dir> --max-hitters 60
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

from . import playlist as PL
from . import videocut as V

MIN_EACH = 100
BAR = 0.40


def sb(r: float) -> float:
    return 2 * r / (1 + r) if r > -1 else float("nan")


def hitters_from_games(games: list[int], cap: int) -> list[int]:
    ids = []
    for g in games:
        for p in V.game_pitches(g):
            b = p.get("batter")
            if b and b not in ids:
                ids.append(b)
    return ids[:cap]


def boot_r(a, b, reps=2000, seed=11):
    a, b = np.asarray(a), np.asarray(b)
    rng = np.random.default_rng(seed)
    rs = []
    for _ in range(reps):
        i = rng.integers(0, len(a), len(a))
        if a[i].std() > 0 and b[i].std() > 0:
            rs.append(np.corrcoef(a[i], b[i])[0, 1])
    return np.percentile(rs, [2.5, 97.5])


def run(ids: list[int], seasons: list[int], work: pathlib.Path) -> dict:
    res = {}
    for trait, fam in (("ride", "FB"), ("run", "BRK")):
        res[trait] = dict(odd=[], even=[], y1=[], y2=[], ids_split=[], ids_yoy=[])
    skipped = []
    for k, hid in enumerate(ids):
        try:
            hist = PL.hitter_history(hid, seasons, work / "hitters")
        except Exception as e:
            skipped.append((hid, f"{type(e).__name__}"))
            continue
        gp = sorted({r.get("game_pk") for r in hist if r.get("game_pk")})
        par = {g: i % 2 for i, g in enumerate(gp)}
        for trait, fam in (("ride", "FB"), ("run", "BRK")):
            odd = [r for r in hist if par.get(r.get("game_pk")) == 0]
            even = [r for r in hist if par.get(r.get("game_pk")) == 1]
            a = PL.trait_slope(odd, fam, trait, min_swings=MIN_EACH, boot=0)
            b = PL.trait_slope(even, fam, trait, min_swings=MIN_EACH, boot=0)
            if a["ok"] and b["ok"]:
                res[trait]["odd"].append(a["slope"]); res[trait]["even"].append(b["slope"]); res[trait]["ids_split"].append(hid)
            y1 = PL.trait_slope([r for r in hist if r["_season"] == seasons[-2]], fam, trait, min_swings=MIN_EACH, boot=0)
            y2 = PL.trait_slope([r for r in hist if r["_season"] == seasons[-1]], fam, trait, min_swings=MIN_EACH, boot=0)
            if y1["ok"] and y2["ok"]:
                res[trait]["y1"].append(y1["slope"]); res[trait]["y2"].append(y2["slope"]); res[trait]["ids_yoy"].append(hid)
        print(f"{k + 1}/{len(ids)} {hid}", flush=True)
    out = dict(skipped=skipped, traits={})
    for trait, d in res.items():
        t = {}
        for name, x, y in (("split_half", d["odd"], d["even"]), ("year_over_year", d["y1"], d["y2"])):
            if len(x) >= 8:
                r = float(np.corrcoef(x, y)[0, 1])
                lo, hi = boot_r(x, y)
                t[name] = dict(n=len(x), r=round(r, 3), ci=[round(float(lo), 3), round(float(hi), 3)], corrected=round(sb(r), 3) if name == "split_half" else None)
            else:
                t[name] = dict(n=len(x), r=None)
        sh = t["split_half"]
        t["passes_bar"] = bool(sh.get("r") is not None and sh["corrected"] >= BAR and sh["ci"][0] > 0)
        out["traits"][trait] = t
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", required=True)
    ap.add_argument("--seasons", default="2023,2024,2025")
    ap.add_argument("--max-hitters", type=int, default=60)
    ap.add_argument("--work", required=True)
    a = ap.parse_args(argv)
    work = pathlib.Path(a.work)
    ids = hitters_from_games([int(g) for g in a.games.split(",")], a.max_hitters)
    out = run(ids, [int(s) for s in a.seasons.split(",")], work)
    out["hitters_considered"] = len(ids)
    (work / "reliability.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
