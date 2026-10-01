"""Single-A feasibility, from public data: how much evidence does a plan stand on when the data is minor-league sized?

Uses Savant's public minor league search (Triple-A since 2023, Florida State League Single-A since 2021; fetched with
`python -m gameplan.bulk --minors --league data/milb25 --start 2025-04-01 --end 2025-09-21`) beside MLB 2025.
California League, Visalia's league, is not in the public feed, so this is a stand-in for sample sizes and data
completeness, not for Visalia itself.

Part 1  coverage: pitches, games, hitters and starters by sample size; share of swings with pitch shape, batted-ball
        quality and bat tracking present.
Part 2  plan support: for a sample of real starter games after the cutoff (lineups, hitters and starters fit only on
        earlier games), the share of plan cells that are thin (call withheld for lack of evidence), no call, GO and
        NO_GO, and the typical effective number of the hitter's own swings behind a cell.

    python -m gameplan.feasibility --dirs data/league data/milb25 --labels MLB MiLB --cutoff 2025-07-01
"""
from __future__ import annotations

import argparse
import csv
import glob
import pathlib
from collections import Counter

import numpy as np

from .mockup import Engine, load_events, load_pitcher_rows
from .savant import parse_swings


def coverage(directory: str, label: str):
    ev, games, starts = [], set(), Counter()
    for f in sorted(glob.glob(str(pathlib.Path(directory) / "*.csv"))):
        text = open(f, encoding="utf-8-sig").read()
        ev += parse_swings(text, include_takes=True)
        for r in csv.DictReader(text.splitlines()):
            games.add(r["game_pk"])
            if r["inning"] == "1" and r["at_bat_number"] and int(r["at_bat_number"]) <= 3:
                starts[(r["game_pk"], r["pitcher"])] += 1
    sw = [s for s in ev if s.swing]
    per_h = Counter(s.batter for s in sw)
    per_p = Counter(p for (_, p) in starts)
    shape = np.mean([None not in (s.velo, s.ivb, s.hb, s.vaa) for s in ev])
    bat = np.mean([s.attack_angle is not None for s in sw])
    bip = [s for s in sw if s.xwoba is not None or s.woba is not None]
    xw = np.mean([s.xwoba is not None for s in bip]) if bip else float("nan")
    q = lambda c, n: sum(v >= n for v in c.values())
    print(f"\n  {label}: {len(ev)} pitches, {len(games)} games, {len(sw)} swings")
    print(f"    hitters with 100+ / 300+ / 800+ tracked swings: {q(per_h, 100)} / {q(per_h, 300)} / {q(per_h, 800)} "
          f"(median {np.median(list(per_h.values())):.0f} per hitter)")
    print(f"    starters with 5+ / 10+ / 20+ starts: {q(per_p, 5)} / {q(per_p, 10)} / {q(per_p, 20)} "
          f"(median {np.median(list(per_p.values())):.0f} starts per starter)")
    print(f"    share of pitches with full shape fields {shape:.1%}; swings with bat tracking {bat:.1%}; "
          f"balls in play with Savant xwOBA {xw:.1%}")


def support(directory: str, label: str, cutoff: str, n_games: int, seed: int = 5, min_starts: int = 3):
    events = load_events(directory, cutoff)
    files = [f for f in sorted(glob.glob(str(pathlib.Path(directory) / "*.csv"))) if pathlib.Path(f).stem >= cutoff]
    rng = np.random.default_rng(seed)
    games = []
    for f in files:
        seen = {}
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            if r["inning"] == "1":
                seen.setdefault((r["game_pk"], r["pitcher"]), pathlib.Path(f).stem)
        games += [(d, g, p) for (g, p), d in seen.items()]
    rng.shuffle(games)
    base = Engine(events, [], cutoff, "0")
    acc = Counter()
    n_h, swings_h, starts_p = [], [], []
    done = 0
    for date, game, starter in games:
        if done >= n_games:
            break
        rows = load_pitcher_rows(directory, starter, cutoff)
        n_starts = len({p.game_pk for p in rows})
        if n_starts < min_starts:
            continue
        grows = [s for s in parse_swings(open(pathlib.Path(directory) / f"{date}.csv", encoding="utf-8-sig").read(),
                                         include_takes=True) if s.game_pk == game and s.pitcher == starter]
        lineup = []
        for s in sorted(grows, key=lambda s: (s.at_bat, s.pitch_no)):
            if s.batter not in lineup:
                lineup.append(s.batter)
        eng = base.retarget(rows, starter)
        starts_p.append(n_starts)
        for h in lineup[:9]:
            st = [s.stand for s in grows if s.batter == h and s.stand]
            stand = max(set(st), key=st.count) if st else "R"
            sw = [s for s in eng.by_hitter[h] if s.swing]
            swings_h.append(len(sw))
            hit = eng.hitter(h)
            for b, s in ((0, 0), (1, 1), (0, 2), (3, 1)):
                snap = eng.snapshot(h, 1, b, s, stand, hit)
                for c in snap.cells.values():
                    acc["cells"] += 1
                    acc["thin"] += bool(c.get("low_support"))
                    acc[c["cls"]] += 1
                    n_h.append(c.get("n_h", 0.0))
        done += 1
    tot = acc["cells"] or 1
    print(f"\n  {label}: {done} starter games, starters had a median {np.median(starts_p):.0f} prior starts, "
          f"hitters a median {np.median(swings_h):.0f} tracked swings before the cutoff")
    print(f"    cells: GO {acc['GO'] / tot:.1%}, NO_GO {acc['NO_GO'] / tot:.1%}, no call {acc['CONDITIONAL'] / tot:.1%} "
          f"(of which thin evidence {acc['thin'] / tot:.1%}); effective hitter swings behind a cell: median {np.median(n_h):.1f}, "
          f"25th pct {np.percentile(n_h, 25):.1f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    ap.add_argument("--n-games", type=int, default=25)
    a = ap.parse_args(argv)
    print("== Part 1: coverage")
    for d, l in zip(a.dirs, a.labels):
        coverage(d, l)
    print(f"\n== Part 2: plan support, fit before {a.cutoff}")
    for d, l in zip(a.dirs, a.labels):
        support(d, l, a.cutoff, a.n_games)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
