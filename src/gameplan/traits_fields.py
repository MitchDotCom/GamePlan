"""Field audit (plan WS1.1): which bat-tracking fields exist on which swings, by season.

If a field such as attack angle is recorded only when the bat meets the ball, any analysis that uses it on swings that missed
is selecting on the outcome. This prints the share of non-null values per field, split by swing result, so that is known
before any model is trusted.

    python -m gameplan.traits_fields --dir 2025=data/b3 --dir 2024=data/b24 > docs/traits_fields.txt"""
from __future__ import annotations

import argparse
import csv
import pathlib
from collections import defaultdict

from .savant import SWING_DESCRIPTIONS, WHIFF_DESCRIPTIONS

FIELDS = ("bat_speed", "swing_length", "attack_angle", "attack_direction", "swing_path_tilt",
          "intercept_ball_minus_batter_pos_x_inches", "intercept_ball_minus_batter_pos_y_inches")


def _kind(desc: str) -> str | None:
    if desc not in SWING_DESCRIPTIONS or desc in ("foul_bunt", "missed_bunt", "bunt_foul_tip"):
        return None
    return "whiff" if desc in WHIFF_DESCRIPTIONS else "in_play" if desc == "hit_into_play" else "foul"


def audit(folder: str):
    n = defaultdict(int)
    have = defaultdict(lambda: defaultdict(int))
    for f in sorted(pathlib.Path(folder).glob("*.csv")):
        with open(f, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                k = _kind(row.get("description", ""))
                if k is None:
                    continue
                n[k] += 1
                for fld in FIELDS:
                    if row.get(fld) not in (None, "", "null", "NA"):
                        have[k][fld] += 1
    return n, have


def report(label: str, folder: str) -> str:
    n, have = audit(folder)
    out = [f"== {label} ({folder}): swings by result: " + ", ".join(f"{k} {n[k]}" for k in ("whiff", "foul", "in_play"))]
    out.append(f"   {'field':44s} " + " ".join(f"{k:>9s}" for k in ("whiff", "foul", "in_play")))
    for fld in FIELDS:
        out.append(f"   {fld:44s} " + " ".join(f"{(have[k][fld] / n[k] if n[k] else float('nan')):9.3f}" for k in ("whiff", "foul", "in_play")))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="append", required=True, help="LABEL=folder")
    a = ap.parse_args(argv)
    for d in a.dir:
        label, folder = d.split("=", 1)
        print(report(label, folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
