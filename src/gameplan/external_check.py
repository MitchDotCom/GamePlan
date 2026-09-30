"""External replication: does this method's per-hitter swing/take decision value track the published one?

Baseball Savant publishes each hitter's Swing/Take run value (runs_all, and by attack zone). It is built
the same way as this decision layer: for each pitch, value the action taken against the alternative
using outcome probabilities and count-based run values. If the method is sound, a league-average version
of it (no hitter-specific term, so it matches Savant's population-level approach) should rank hitters
similarly. Zone definitions differ (Savant's heart / shadow / chase / waste are their own), so only the
total and rough zone groupings are compared, by rank correlation and Pearson correlation, not by level.

    python -m gameplan.external_check --league data/league --swingtake swingtake.csv
    (swingtake.csv: https://baseballsavant.mlb.com/leaderboard/swing-take?year=2025&type=All&group=Batter&min=q&csv=true)"""
from __future__ import annotations

import argparse
import csv
import glob
import pathlib
import random

import numpy as np

from .constants import value as _const
from .decision import DEFAULT, evs_np, realized_value
from .savant import parse_swings
from .shape import ContactModel
from .zone import CalledStrikeModel

MAX_PITCHES = 700        # per hitter, sampled; totals are scaled to the hitter's full pitch count


def _spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--swingtake", required=True)
    ap.add_argument("--min-pitches", type=int, default=1500)
    a = ap.parse_args(argv)
    saved = {}
    for r in csv.DictReader(open(a.swingtake, encoding="utf-8-sig")):
        if int(r["pitches"]) >= a.min_pitches:
            saved[r["player_id"]] = {k: float(r[k]) for k in ("runs_all", "runs_heart", "runs_shadow", "runs_chase", "runs_waste")} | {"pitches": int(r["pitches"])}
    by = {}
    for f in sorted(glob.glob(str(pathlib.Path(a.league) / "*.csv"))):
        for s in parse_swings(open(f, encoding="utf-8-sig").read(), include_takes=True):
            by.setdefault(s.batter, []).append(s)
    league_swings = [s for r in by.values() for s in r if s.swing]
    zm = CalledStrikeModel([s for r in by.values() for s in r if not s.swing])
    lm = ContactModel([], league_swings, mode="shape")
    rng = random.Random(0)
    scale = _const("WOBA_SCALE_2025")
    mine, theirs, zone_mine = [], [], {"heart": [], "shadow": [], "outside": []}
    zone_theirs = {"heart": [], "shadow": [], "outside": []}
    ids = [h for h in saved if h in by]
    print(f"hitters in both: {len(ids)} (Savant published {len(saved)})")
    for h in ids:
        rows = [s for s in by[h] if s.x_away is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)]
        if len(rows) < 300:
            continue
        samp = rng.sample(rows, min(len(rows), MAX_PITCHES))
        Q = np.array([(s.x_away, s.z, s.velo, s.ivb, s.hb, s.vaa) for s in samp], float)
        p = lm.predict(Q, use_hitter=False)
        sb = np.array([s.sz_bot or 1.5 for s in samp])
        st = np.array([s.sz_top or 3.5 for s in samp])
        bal = np.array([s.balls for s in samp])
        stk = np.array([s.strikes for s in samp])
        pcs = zm.p(Q[:, 0], Q[:, 1], sb, st, strikes=stk)
        sw, tk = evs_np(p["whiff"], p["foul"], p["xw"], pcs, bal, stk)
        swung = np.array([s.swing for s in samp])
        dv = np.where(swung, sw - tk, tk - sw) / scale                      # runs per pitch, action taken minus alternative
        k = saved[h]["pitches"] / len(samp)
        mine.append(dv.sum() * k)
        theirs.append(saved[h]["runs_all"])
        for name, m in (("heart", pcs > 0.9), ("shadow", (pcs <= 0.9) & (pcs >= 0.1)), ("outside", pcs < 0.1)):
            zone_mine[name].append(dv[m].sum() * k)
        zone_theirs["heart"].append(saved[h]["runs_heart"])
        zone_theirs["shadow"].append(saved[h]["runs_shadow"])
        zone_theirs["outside"].append(saved[h]["runs_chase"] + saved[h]["runs_waste"])
    # Savant's swing/take values are REALIZED production by zone (actual outcomes valued with run
    # expectancy), not the expected value of the choice. Replicate that quantity with this pipeline's count
    # values and outcomes: per pitch, value of the state reached minus value of the count before it.
    prod = {"all": [], "heart": [], "shadow": [], "outside": []}
    prod_theirs = {"all": [], "heart": [], "shadow": [], "outside": []}
    for h in ids:
        rows = [s for s in by[h] if s.x_away is not None and s.balls <= 3 and s.strikes <= 2]
        if len(rows) < 300:
            continue
        x = np.array([s.x_away for s in rows]); z = np.array([s.z for s in rows])
        sb = np.array([s.sz_bot or 1.5 for s in rows]); st = np.array([s.sz_top or 3.5 for s in rows])
        pcs = zm.p(x, z, sb, st, strikes=np.array([s.strikes for s in rows]))
        vals = np.array([(realized_value(s.swing, s.whiff, s.xwoba, s.take_call, s.balls, s.strikes, DEFAULT)
                          if realized_value(s.swing, s.whiff, s.xwoba, s.take_call, s.balls, s.strikes, DEFAULT) is not None else np.nan)
                         - DEFAULT.table[(s.balls, s.strikes)] for s in rows]) / scale
        ok = ~np.isnan(vals)
        k = saved[h]["pitches"] / max(ok.sum(), 1)
        prod["all"].append(np.nansum(vals) * k)
        for name, m in (("heart", pcs > 0.9), ("shadow", (pcs <= 0.9) & (pcs >= 0.1)), ("outside", pcs < 0.1)):
            prod[name].append(np.nansum(vals[m]) * k)
        prod_theirs["all"].append(saved[h]["runs_all"]); prod_theirs["heart"].append(saved[h]["runs_heart"])
        prod_theirs["shadow"].append(saved[h]["runs_shadow"]); prod_theirs["outside"].append(saved[h]["runs_chase"] + saved[h]["runs_waste"])
    mine, theirs = np.array(mine), np.array(theirs)
    print(f"\nper-hitter total decision value, this method (league-average model) vs Savant runs_all, n={len(mine)}")
    print(f"  Pearson {np.corrcoef(mine, theirs)[0, 1]:+.3f}   Spearman {_spearman(mine, theirs):+.3f}")
    print("by rough zone (my zones by called-strike probability: heart > 0.9, shadow 0.1 to 0.9, outside < 0.1; Savant heart, shadow, chase + waste):")
    for name in ("heart", "shadow", "outside"):
        m, t = np.array(zone_mine[name]), np.array(zone_theirs[name])
        print(f"  {name:<8} Pearson {np.corrcoef(m, t)[0, 1]:+.3f}   Spearman {_spearman(m, t):+.3f}")
    print(f"\nrealized production per hitter (this pipeline's count values and outcomes) vs Savant swing/take run values, n={len(prod['all'])}")
    for name in ("all", "heart", "shadow", "outside"):
        m, t = np.array(prod[name]), np.array(prod_theirs[name])
        print(f"  {name:<8} Pearson {np.corrcoef(m, t)[0, 1]:+.3f}   Spearman {_spearman(m, t):+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
