"""Does the angle between the bat path and the pitch path predict whiffs and damage?  (exploratory, league level, public Savant)

Vertical bat-ball angle (VBA) = attack angle + |vertical approach angle|. The bat travels up at the attack angle; the ball
arrives travelling down at the vertical approach angle (negative in Savant). A small VBA means the two paths are close to
the same plane at contact. Savant bat tracking starts mid 2025 for attack angle.

Reports, per 3 degree VBA bin:  swings, whiff rate, squared-up rate on balls in play, xwOBA on contact.
Also hitter-demeaned (each metric minus that hitter's own mean), so the table is not just "better hitters swing differently".
Descriptive only. A bin pattern here does not prove a causal effect; it says whether the angle carries any signal at all.

    python -m gameplan.plane_match --league data/league > docs/plane_match.txt
"""
from __future__ import annotations

import argparse
import glob
import pathlib
from collections import defaultdict

import numpy as np

from .savant import parse_swings

BIN = 3.0
FAMILY = {"FF": "Fastball", "SI": "Fastball", "FC": "Fastball", "SL": "Breaking", "ST": "Breaking", "SV": "Breaking",
          "CU": "Breaking", "KC": "Breaking", "CS": "Breaking", "CH": "Offspeed", "FS": "Offspeed", "FO": "Offspeed"}


def load(league_dir: str):
    rows = []
    for f in sorted(glob.glob(str(pathlib.Path(league_dir) / "*.csv"))):
        for s in parse_swings(open(f, encoding="utf-8-sig").read()):
            if s.attack_angle is not None and s.vaa is not None and s.bat_speed is not None:
                rows.append(s)
    return rows


def table(rows, label):
    by_h = defaultdict(list)
    for i, s in enumerate(rows):
        by_h[s.batter].append(i)
    whiff = np.array([float(s.whiff) for s in rows])
    xw = np.array([s.xwoba if s.xwoba is not None else np.nan for s in rows])
    sq = np.array([float(s.squared_up) if s.squared_up is not None else np.nan for s in rows])
    vba = np.array([s.attack_angle - s.vaa for s in rows])
    dw, dx, dq = whiff.copy(), xw.copy(), sq.copy()
    for h, idx in by_h.items():
        if len(idx) < 50:
            dw[idx] = dx[idx] = dq[idx] = np.nan
            continue
        for a, d in ((whiff, dw), (xw, dx), (sq, dq)):
            d[idx] = a[idx] - np.nanmean(a[idx])
    lo = np.floor(np.percentile(vba, 1) / BIN) * BIN
    hi = np.ceil(np.percentile(vba, 99) / BIN) * BIN
    print(f"\n{label}: {len(rows)} swings with bat tracking and approach angle; VBA median {np.median(vba):.1f}, "
          f"1st to 99th pct {lo:.0f} to {hi:.0f} degrees")
    print(f"{'VBA bin':>10} {'swings':>8} {'whiff':>7} {'whiff vs own':>13} {'squared up':>11} {'sq vs own':>10} {'xwOBAcon':>9} {'xw vs own':>10}")
    for b in np.arange(lo, hi, BIN):
        m = (vba >= b) & (vba < b + BIN)
        if m.sum() < 300:
            continue
        print(f"{b:>5.0f}-{b + BIN:<4.0f} {m.sum():>8} {np.nanmean(whiff[m]):>7.3f} {np.nanmean(dw[m]):>+13.3f} "
              f"{np.nanmean(sq[m]):>11.3f} {np.nanmean(dq[m]):>+10.3f} {np.nanmean(xw[m]):>9.3f} {np.nanmean(dx[m]):>+10.3f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    a = ap.parse_args(argv)
    rows = load(a.league)
    table(rows, "All pitches")
    for fam in ("Fastball", "Breaking", "Offspeed"):
        table([s for s in rows if FAMILY.get(s.pitch_type) == fam], fam)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
