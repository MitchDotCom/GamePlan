"""Empirical base-out adjustments to outcome values, fit from Statcast run expectancy.

For every plate appearance, the last pitch's delta_run_exp is the run-expectancy change that outcome
produced in its base-out state. Comparing a state's average for each outcome class (strikeout, walk
or HBP, ball in play) with the average across all states gives how much that state changes what the
outcome is worth. Converted to wOBA scale with the standard 1.2 factor. Count mix is not controlled,
which is a known approximation.

    python -m gameplan.baseout --batters data/b2 --out src/gameplan/baseout_2025.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import pathlib
from collections import defaultdict

WOBA_SCALE = 1.2
K_EVENTS = {"strikeout", "strikeout_double_play"}
BB_EVENTS = {"walk", "intent_walk", "hit_by_pitch"}
SKIP_EVENTS = {"truncated_pa", "catcher_interf", "batter_interference"}


def outcome_class(event: str) -> str | None:
    if event in SKIP_EVENTS:
        return None
    return "K" if event in K_EVENTS else "BB" if event in BB_EVENTS else "BIP"


def state_key(outs: int, on1: bool, on2: bool, on3: bool) -> str:
    return f"{outs}|{int(on1)}{int(on2)}{int(on3)}"


def fit(texts, date_min: str = "", date_max: str = "9999") -> dict:
    """Returns {"pooled": {cls: mean_rv}, "states": {key: {cls: [delta_wOBA, n]}}}."""
    by_state: dict = defaultdict(lambda: defaultdict(list))
    allv: dict = defaultdict(list)
    for text in texts:
        for r in csv.DictReader(io.StringIO(text)):
            if not (date_min <= (r.get("game_date") or date_min) < date_max):
                continue
            ev = r.get("events")
            if not ev or not r.get("delta_run_exp") or r.get("outs_when_up") in (None, ""):
                continue
            cls = outcome_class(ev)
            if cls is None:
                continue
            key = state_key(int(float(r["outs_when_up"])), *(bool(float(r.get(k) or 0)) for k in ("on_1b", "on_2b", "on_3b")))
            rv = float(r["delta_run_exp"])
            by_state[key][cls].append(rv)
            allv[cls].append(rv)
    pooled = {c: sum(v) / len(v) for c, v in allv.items()}
    states = {}
    for key, d in by_state.items():
        states[key] = {c: [WOBA_SCALE * (sum(v) / len(v) - pooled[c]), len(v)] for c, v in d.items()}
    return {"pooled_run_value": pooled, "states": states}


def load(path: str | None = None) -> dict:
    p = pathlib.Path(path) if path else pathlib.Path(__file__).with_name("baseout_2025.json")
    return json.loads(p.read_text()) if p.exists() else {"pooled_run_value": {}, "states": {}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batters", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    texts = (open(p, encoding="utf-8-sig").read() for p in sorted(glob.glob(str(pathlib.Path(a.batters) / "*.csv"))))
    table = fit(texts)
    pathlib.Path(a.out).write_text(json.dumps(table, indent=1))
    print("state (outs|1B 2B 3B)   dK    dBB   dBIP   n_K  n_BB  n_BIP   [wOBA-scale change vs all states]")
    for key in sorted(table["states"]):
        d = table["states"][key]
        g = lambda c: d.get(c, [float('nan'), 0])
        print(f"  {key:<8}  {g('K')[0]:+.3f} {g('BB')[0]:+.3f} {g('BIP')[0]:+.3f}   {g('K')[1]:>5} {g('BB')[1]:>5} {g('BIP')[1]:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
