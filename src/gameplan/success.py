"""How we decide whether this works: pre-registered pass criteria, published benchmarks, and a scorecard.

Criteria are fixed here BEFORE results are read, so a result cannot be reinterpreted afterwards. Change
a criterion only with a dated note in CRITERIA_LOG, and rerun everything.

Seven measures, in the order they can be tested:

  1 numbers   constants match published sources; derived values reproduce published benchmarks
  2 calibrated  predicted swing and take values match realized, overall and by segment
  3 skill     hitter-specific data beats league-only on held-out data, including year over year
  4 separates  the call separates pitches where swinging beat taking from those where taking did
  5 actionable  hitters can follow it (compliance measured; recognition window feasible)
  6 helps     process outcomes improve in a pilot with the power to detect a stated effect
  7 honest    plan cells carry sample size and uncertainty and low-support cells are withheld

Studies write their headline numbers with record(); scorecard() compares them to the criteria.

    python -m gameplan.success --league data/league          # benchmark checks against league-wide data
    python -m gameplan.success --scorecard                   # print the scorecard from recorded results
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import pathlib
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

RESULTS_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "scorecard_results.json"

CRITERIA_LOG = [
    "2026-09-29: criteria written before the corrected-data reruns; thresholds below were not adjusted after seeing them.",
]


@dataclass(frozen=True)
class Criterion:
    key: str
    measure: int
    description: str
    op: str            # ">=", "<=", "between", "abs<="
    threshold: tuple   # one or two numbers
    source: str = ""   # where the threshold comes from; "choice" if it is mine


CRITERIA: list[Criterion] = [
    # 1 numbers
    Criterion("bench.woba_scale_used", 1, "wOBA scale in code equals FanGraphs 2025", "between", (1.257, 1.257), "FanGraphs Guts"),
    Criterion("bench.count_run_values_max_rel_err", 1, "count run values vs published (0-0 strike, 0-1 ball, 1-1 strike): max relative error",
              "<=", (0.15,), "choice; published values from Savant/Tango count tables"),
    Criterion("bench.league_woba_abs_err", 1, "league-wide wOBA (published weights, proper denominator) vs FanGraphs .314", "<=", (0.004,), "choice"),
    Criterion("bench.tto_1_to_2_pts", 1, "league-wide wOBA increase TTO1 to TTO2 vs starters, points", "between", (5.0, 16.0),
              "published +8 to +13 (Tango/Lichtman; Brill et al. 13.4) widened by 3 each side"),
    Criterion("bench.ivb_ff_in", 1, "league mean four-seam IVB, inches", "between", (14.0, 18.0), "MLB glossary: about +16 in 2024, +/-2"),
    Criterion("bench.ivb_cu_in", 1, "league mean curveball IVB, inches", "between", (-12.0, -8.0), "MLB glossary: about -10 in 2024, +/-2"),
    # 2 calibrated
    Criterion("cal.swing_slope", 2, "swing EV calibration slope", "between", (0.95, 1.05), "choice"),
    Criterion("cal.take_slope", 2, "take EV calibration slope", "between", (0.95, 1.05), "choice"),
    Criterion("cal.max_decile_gap", 2, "largest decile gap, realized minus predicted (wOBA points)", "abs<=", (0.02,), "choice"),
    Criterion("cal.max_segment_gap", 2, "largest segment gap (count, family, side, TTO) with CI excluding 0", "abs<=", (0.02,), "choice"),
    # 3 skill
    Criterion("skill.whiff_yoy_ci_low", 3, "year-over-year whiff Brier skill vs league, CI lower bound", ">=", (0.0,), "choice"),
    Criterion("skill.xw_yoy_ci_low", 3, "year-over-year xwOBAcon MSE skill vs league, CI lower bound", ">=", (0.0,), "choice"),
    # 4 separates
    Criterion("sep.disagree_ci_low", 4, "hitter-vs-league disagreement: swing-take gap difference, CI lower bound", ">=", (0.0,), "choice"),
    Criterion("sep.count_removal_hurts", 4, "S lost when count awareness is removed, CI upper bound", "<=", (0.0,), "choice"),
    # 5 actionable
    Criterion("act.recognition_feasible", 5, "hitters recognize pitch type before the decision point (needs pilot data)", ">=", (1.0,), "not measurable on MLB export"),
    # 6 helps
    Criterion("pilot.mde_runs_per_pitch", 6, "pilot minimum detectable difference, runs per pitch, must be <= expected effect", "<=", (0.02,), "expected effect from compliance x gap"),
    # 7 honest
    Criterion("honest.confident_gap_diff_ci_low", 7, "confident GO pitches separate swing from take better than thin-support GO pitches: CI lower bound of the gap difference (runs)", ">=", (0.0,), "choice"),
]

_BY_KEY = {c.key: c for c in CRITERIA}


def record(key: str, value: float, note: str = "", path: pathlib.Path = RESULTS_PATH) -> None:
    """Store a headline number from a study run."""
    data = json.loads(path.read_text()) if path.exists() else {}
    data[key] = {"value": value, "note": note}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True))


def _passes(c: Criterion, v: float) -> bool:
    if c.op == ">=":
        return v >= c.threshold[0]
    if c.op == "<=":
        return v <= c.threshold[0]
    if c.op == "abs<=":
        return abs(v) <= c.threshold[0]
    return c.threshold[0] <= v <= c.threshold[1]


def scorecard(path: pathlib.Path = RESULTS_PATH) -> str:
    data = json.loads(path.read_text()) if path.exists() else {}
    lines = ["| # | Criterion | Rule | Result | Status |", "|---|---|---|---|---|"]
    counts = defaultdict(int)
    for c in CRITERIA:
        rule = {">=": f">= {c.threshold[0]}", "<=": f"<= {c.threshold[0]}", "abs<=": f"|x| <= {c.threshold[0]}",
                "between": f"in [{c.threshold[0]}, {c.threshold[-1]}]"}[c.op]
        if c.key in data:
            v = data[c.key]["value"]
            ok = _passes(c, v)
            status = "PASS" if ok else "FAIL"
            res = f"{v:.4g}"
        else:
            status, res = "NOT MEASURED", "-"
        counts[status] += 1
        lines.append(f"| {c.measure} | {c.description} | {rule} | {res} | {status} |")
    lines.append("")
    lines.append("  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


# ------------------------------------------------------------------ published-benchmark checks on league-wide data

PUBLISHED_COUNT_RV = {"0-0 strike": -0.037, "0-1 ball": 0.024, "1-1 strike": -0.054}   # runs, per search summary of Savant/Tango tables


def league_benchmarks(league_dir: str, write: bool = True) -> dict:
    """Checks that need every pitch of the season: league wOBA, TTO penalty vs starters, IVB by pitch type."""
    from .constants import value
    from .decision import DEFAULT, event_woba
    from .shape import filter_starts, parse_pitches

    pa_w = []
    tto = defaultdict(list)
    ivb = defaultdict(list)
    all_pitches = []
    starts_keys = set()
    rows_all = []
    for path in sorted(glob.glob(str(pathlib.Path(league_dir) / "*.csv"))):
        text = open(path, encoding="utf-8-sig").read()
        pitches = parse_pitches(text)
        all_pitches += pitches
        for r in csv.DictReader(io.StringIO(text)):
            rows_all.append((r["game_pk"], r["at_bat_number"], r["pitch_number"], r["pitch_type"], r["events"],
                             r["woba_value"], r["n_thruorder_pitcher"], r["pfx_z"]))
    starts = filter_starts(all_pitches)
    starts_keys = {(p.game_pk, p.at_bat, p.pitch_no) for p in starts}
    for gp, ab, pn, pt, ev, wv, nt, pz in rows_all:
        if pt in ("FF", "CU") and pz not in ("", None):
            ivb[pt].append(float(pz) * 12)
        w = event_woba(ev)
        if w is not None:
            pa_w.append(w)
            if nt and (gp, int(float(ab)), int(float(pn))) in starts_keys:
                tto[min(int(float(nt)), 3)].append(w)
    out = {
        "bench.woba_scale_used": value("WOBA_SCALE_2025"),
        "bench.league_woba_abs_err": abs(statistics.mean(pa_w) - value("LEAGUE_WOBA_2025")),
        "bench.tto_1_to_2_pts": 1000 * (statistics.mean(tto[2]) - statistics.mean(tto[1])),
        "bench.ivb_ff_in": statistics.mean(ivb["FF"]),
        "bench.ivb_cu_in": statistics.mean(ivb["CU"]),
    }
    V, sc = DEFAULT.table, value("WOBA_SCALE_2025")
    mine = {"0-0 strike": (V[(0, 1)] - V[(0, 0)]) / sc, "0-1 ball": (V[(1, 1)] - V[(0, 1)]) / sc,
            "1-1 strike": (V[(1, 2)] - V[(1, 1)]) / sc}
    out["bench.count_run_values_max_rel_err"] = max(abs(mine[k] - PUBLISHED_COUNT_RV[k]) / abs(PUBLISHED_COUNT_RV[k])
                                                    for k in mine)
    detail = {
        "league wOBA (this data)": statistics.mean(pa_w), "PAs": len(pa_w),
        "TTO wOBA": {t: (statistics.mean(v), len(v)) for t, v in tto.items()},
        "TTO 2 to 3+ pts": 1000 * (statistics.mean(tto[3]) - statistics.mean(tto[2])),
        "count run values (mine)": mine, "published": PUBLISHED_COUNT_RV,
    }
    if write:
        for k, v in out.items():
            record(k, v)
    return {"metrics": out, "detail": detail}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", help="dir of league-wide per-day CSVs (bulk.fetch_league_days)")
    ap.add_argument("--scorecard", action="store_true")
    a = ap.parse_args(argv)
    if a.league:
        res = league_benchmarks(a.league)
        for k, v in res["metrics"].items():
            c = _BY_KEY[k]
            print(f"  {k:<40} {v:>10.4f}  {'PASS' if _passes(c, v) else 'FAIL'}   ({c.description})")
        print("  detail:", json.dumps(res["detail"], indent=1, default=str))
    if a.scorecard or not a.league:
        print(scorecard())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
