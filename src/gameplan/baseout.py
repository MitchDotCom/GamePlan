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


def score_bucket(diff: int) -> int:
    """Batting team's lead: 0 down 4+, 1 down 2-3, 2 down 1, 3 tied, 4 up 1, 5 up 2-3, 6 up 4+."""
    return 0 if diff <= -4 else 1 if diff <= -2 else 2 if diff == -1 else 3 if diff == 0 else 4 if diff == 1 else 5 if diff <= 3 else 6


def inning_bucket(inning: int) -> int:
    return 0 if inning <= 3 else 1 if inning <= 6 else 2 if inning <= 8 else 3


def si_key(diff: int, inning: int) -> str:
    return f"{score_bucket(diff)}|{inning_bucket(inning)}"


def fit_score_inning(texts, date_min: str = "", date_max: str = "9999") -> dict:
    """How score and inning change what each outcome is worth beyond its run value.

    Per (lead bucket, inning bucket): leverage L = slope of the batting team's win-expectancy change on
    run-expectancy change over plate-appearance-ending pitches (win probability per run). Each outcome's
    win-expectancy change divided by L is its run-equivalent value in that context; the excess over
    its plain run value, relative to the all-context average, x1.2, is the adjustment in wOBA points."""
    rows = []
    for text in texts:
        for r in csv.DictReader(io.StringIO(text)):
            if not (date_min <= (r.get("game_date") or date_min) < date_max):
                continue
            ev = r.get("events")
            cls = outcome_class(ev) if ev else None
            if cls is None or not r.get("delta_run_exp") or not r.get("delta_home_win_exp"):
                continue
            try:
                diff = int(float(r["bat_score"]) - float(r["fld_score"]))
                inn = int(float(r["inning"]))
            except (KeyError, ValueError):
                continue
            sign = 1.0 if r.get("inning_topbot") == "Bot" else -1.0
            rows.append((si_key(diff, inn), cls, float(r["delta_run_exp"]), sign * float(r["delta_home_win_exp"])))
    by_bucket: dict = defaultdict(list)
    for b, c, rv, we in rows:
        by_bucket[b].append((c, rv, we))

    def slope(items):
        rv = [x[1] for x in items]
        we = [x[2] for x in items]
        mr, mw = sum(rv) / len(rv), sum(we) / len(we)
        var = sum((x - mr) ** 2 for x in rv)
        return sum((x - mr) * (y - mw) for x, y in zip(rv, we)) / var if var else 0.0

    lev = {b: slope(v) for b, v in by_bucket.items() if len(v) >= 200}
    diffs: dict = defaultdict(lambda: defaultdict(list))   # bucket -> class -> [we/L - rv]
    for b, v in by_bucket.items():
        if b not in lev or lev[b] <= 0:
            continue
        for c, rv, we in v:
            diffs[b][c].append(we / lev[b] - rv)
    pooled: dict = defaultdict(list)
    for b in diffs:
        for c, d in diffs[b].items():
            pooled[c] += d
    pooled = {c: sum(d) / len(d) for c, d in pooled.items()}
    mean_l = sum(lev.values()) / len(lev) if lev else 1.0
    return {
        "leverage_wpa_per_run": {b: v for b, v in lev.items()},
        "buckets": {b: {c: [WOBA_SCALE * (sum(d) / len(d) - pooled[c]), len(d)] for c, d in cd.items()}
                    for b, cd in diffs.items()},
        "mean_leverage": mean_l,
    }


def load_score_inning(path: str | None = None) -> dict:
    p = pathlib.Path(path) if path else pathlib.Path(__file__).with_name("scoreinning_2025.json")
    return json.loads(p.read_text()) if p.exists() else {"buckets": {}, "leverage_wpa_per_run": {}}


def load(path: str | None = None) -> dict:
    p = pathlib.Path(path) if path else pathlib.Path(__file__).with_name("baseout_2025.json")
    return json.loads(p.read_text()) if p.exists() else {"pooled_run_value": {}, "states": {}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batters", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--score-inning-out", help="also fit the score / inning table (needs win-expectancy columns)")
    ap.add_argument("--counts-out", help="also write the count value table")
    a = ap.parse_args(argv)
    paths = sorted(glob.glob(str(pathlib.Path(a.batters) / "*.csv")))
    texts = (open(p, encoding="utf-8-sig").read() for p in paths)
    table = fit(texts)
    if a.score_inning_out:
        si = fit_score_inning(open(p, encoding="utf-8-sig").read() for p in paths)
        pathlib.Path(a.score_inning_out).write_text(json.dumps(si, indent=1))
        print("score / inning buckets fit:", len(si["buckets"]))
    if a.counts_out:
        from .decision import fit_count_values
        pathlib.Path(a.counts_out).write_text(fit_count_values(open(p, encoding="utf-8-sig").read() for p in paths).to_json())
    pathlib.Path(a.out).write_text(json.dumps(table, indent=1))
    print("state (outs|1B 2B 3B)   dK    dBB   dBIP   n_K  n_BB  n_BIP   [wOBA-scale change vs all states]")
    for key in sorted(table["states"]):
        d = table["states"][key]
        g = lambda c: d.get(c, [float('nan'), 0])
        print(f"  {key:<8}  {g('K')[0]:+.3f} {g('BB')[0]:+.3f} {g('BIP')[0]:+.3f}   {g('K')[1]:>5} {g('BB')[1]:>5} {g('BIP')[1]:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
