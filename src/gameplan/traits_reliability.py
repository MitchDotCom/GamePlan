"""Trait reliability (plan WS1.2): is a hitter's bat speed, swing length, attack angle and tilt stable enough to carry hitter-specific calls?

Pre-registered floor, fixed before the first run: a trait needs split-half reliability (Spearman-Brown corrected, hitters with at
least MIN_SWINGS tracked swings) of at least FLOOR, in both seasons, on the context-adjusted version. A trait below the floor stays
a league-level quantity and is not used per hitter.

Two versions per trait: RAW (his mean) and ADJUSTED (his mean of swing minus the league expectation for that pitch and count,
from swing_traits.LeagueTraits). Split-half uses SPLITS random halves of each hitter's swings. Year over year is the correlation of
his adjusted mean across 2024 and 2025 for hitters with MIN_SWINGS in both.

    python -m gameplan.traits_reliability --b25 data/b3 --b24 data/b24 > docs/traits_reliability.txt"""
from __future__ import annotations

import argparse
import glob
import pathlib
from collections import defaultdict

import numpy as np

from .savant import parse_swings
from .swing_traits import TRAITS, LeagueTraits, context_row

MIN_SWINGS = 300
FLOOR = 0.4
SPLITS = 200
SEED = 7


def load(folder: str):
    out = []
    for f in sorted(glob.glob(str(pathlib.Path(folder) / "*.csv"))):
        out += [s for s in parse_swings(open(f, encoding="utf-8-sig").read()) if s.bat_speed is not None]
    return out


def per_hitter(swings, lg: LeagueTraits):
    """{batter: {trait: (raw values, adjusted values)}}"""
    d = defaultdict(lambda: {t: ([], []) for t in TRAITS})
    for s in swings:
        c = context_row(s)
        if c is None:
            continue
        for t in lg.coef:
            v = getattr(s, t)
            if v is None:
                continue
            d[s.batter][t][0].append(v)
            d[s.batter][t][1].append(v - float(c @ lg.coef[t]))
    return d


def _sb(r):
    return 2 * r / (1 + r) if r > -1 else float("nan")


def split_half(d, trait, which):
    rng = np.random.default_rng(SEED)
    vals = {h: np.array(v[trait][which]) for h, v in d.items() if len(v[trait][which]) >= MIN_SWINGS}
    if len(vals) < 20:
        return float("nan"), len(vals)
    rs = []
    for _ in range(SPLITS):
        a, b = [], []
        for v in vals.values():
            p = rng.permutation(len(v))
            a.append(v[p[: len(v) // 2]].mean())
            b.append(v[p[len(v) // 2:]].mean())
        rs.append(np.corrcoef(a, b)[0, 1])
    return _sb(float(np.mean(rs))), len(vals)


def yoy(d25, d24, trait):
    hs = [h for h in d25 if h in d24 and len(d25[h][trait][1]) >= MIN_SWINGS and len(d24[h][trait][1]) >= MIN_SWINGS]
    if len(hs) < 20:
        return float("nan"), len(hs)
    return float(np.corrcoef([np.mean(d25[h][trait][1]) for h in hs], [np.mean(d24[h][trait][1]) for h in hs])[0, 1]), len(hs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--b24", required=True)
    a = ap.parse_args(argv)
    s25, s24 = load(a.b25), load(a.b24)
    lg25, lg24 = LeagueTraits(s25), LeagueTraits(s24)
    d25, d24 = per_hitter(s25, lg25), per_hitter(s24, lg24)
    print(f"Floor {FLOOR} (split-half, Spearman-Brown, hitters with {MIN_SWINGS}+ swings), fixed before the run.")
    print(f"{'trait':14s} {'2025 raw':>9s} {'2025 adj':>9s} {'n':>4s} {'2024 raw':>9s} {'2024 adj':>9s} {'n':>4s} {'yoy adj':>8s} {'n':>4s}  verdict")
    for t in TRAITS:
        r25, _ = split_half(d25, t, 0)
        a25, n25 = split_half(d25, t, 1)
        r24, _ = split_half(d24, t, 0)
        a24, n24 = split_half(d24, t, 1)
        y, ny = yoy(d25, d24, t)
        ok = a25 >= FLOOR and a24 >= FLOOR
        print(f"{t:14s} {r25:9.2f} {a25:9.2f} {n25:4d} {r24:9.2f} {a24:9.2f} {n24:4d} {y:8.2f} {ny:4d}  {'PASS' if ok else 'below floor'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
