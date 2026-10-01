"""Independent check of the pitch coordinates and the hitter's strike zone, using the umpires' own calls.

For taken pitches (called strike or ball) it prints the called-strike rate by horizontal position (feet away from the batter,
negative inside) for right- and left-handed batters, and by height as a fraction of each batter's own zone. If the sign
convention or the zone top and bottom were wrong, the two sides would not mirror and the 50% crossings would not sit at the
edges drawn in the viewer (about -0.85 and +0.9 ft horizontally, 0 and 1 in zone fractions).

    python -m gameplan.zone_check --league data/league > docs/zone_geometry_check.txt
"""
import argparse
import collections
import csv
import glob

import numpy as np


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    a = ap.parse_args(argv)
    rows = collections.defaultdict(lambda: [0, 0])
    vert = collections.defaultdict(lambda: [0, 0])
    for f in sorted(glob.glob(f"{a.league}/2025-0[4-9]-*.csv"))[::2]:
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            d = r["description"]
            if d not in ("called_strike", "ball") or r["stand"] not in ("R", "L"):
                continue
            try:
                x, z, b, t = float(r["plate_x"]), float(r["plate_z"]), float(r["sz_bot"]), float(r["sz_top"])
            except ValueError:
                continue
            xa = x if r["stand"] == "R" else -x
            cs = d == "called_strike"
            if b + 0.35 < z < t - 0.35:
                k = (r["stand"], round(xa / 0.1) * 0.1)
                rows[k][0] += cs
                rows[k][1] += 1
            if abs(x) < 0.5:
                k = (r["stand"], round(((z - b) / (t - b)) / 0.1) * 0.1)
                vert[k][0] += cs
                vert[k][1] += 1
    print("Called-strike rate by horizontal position (x_away: negative = inside), mid-height takes")
    print(" x_away     RHB (n)        LHB (n)")
    for xa in np.arange(-1.2, 1.21, 0.1):
        xa = round(float(xa), 1)
        r_, l_ = rows[("R", xa)], rows[("L", xa)]
        if r_[1] > 200 and l_[1] > 200:
            print(f" {xa:+.1f}    {r_[0] / r_[1]:.3f} ({r_[1]:>5})   {l_[0] / l_[1]:.3f} ({l_[1]:>5})")
    print("\nCalled-strike rate by height as a fraction of each batter's own zone (0 = bottom, 1 = top), center takes")
    for zr in np.arange(-0.4, 1.41, 0.1):
        zr = round(float(zr), 1)
        r_, l_ = vert[("R", zr)], vert[("L", zr)]
        if r_[1] > 200 and l_[1] > 200:
            print(f" {zr:+.1f}   R {r_[0] / r_[1]:.3f}  L {l_[0] / l_[1]:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
