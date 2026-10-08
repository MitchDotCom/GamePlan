"""Does a starter's recent history predict the shape mix he uses in his next start? Pre-registered 2026-10-08, before the first run.

Question: the playlists pool a starter's last N starts (recency half-life h) and offer his top 3 (family x nine-pocket) shapes against a batter side.
Does that pool predict what he throws in the NEXT start better than a league-wide default, and which (N, h) is best?

Data: MLB 2025 regular season (data/league daily files) and the Florida State League 2025 feeds (milb_feed cache); Triple-A once fetched.
A start is any pitcher-game with at least 45 tracked pitches (a proxy; relievers rarely reach it). A start enters the test only if the pitcher had at least 3 earlier starts that season.
A (start, batter side) enters only if the start has at least 15 pitches to that side. Shapes: pitch family (FB, BRK, OFF) x pocket (9) = 27 cells; other pitch types are dropped.
Grid: N in {1, 2, 3, 5, 8, all earlier starts}, h in {1, 2, 4, none (equal weights)}. 'all' with no decay is the season-to-date mix. Current default: N=4, h=2.
Selection: lowest mean log-loss of the predicted 27-cell distribution (add-0.5 smoothing) on starts before 2025-07-01. Evaluation: starts on or after 2025-07-01, predictors use only earlier games, so nothing leaks.
Metric on the test period: coverage@3 = share of the start's pitches to that side that fall in the predicted top 3 shapes.
Baselines: league default = top 3 shapes to that side over all pitches before 2025-07-01; oracle = the start's own top 3 (upper bound).
Averages are per pitcher first, then across pitchers; intervals are a bootstrap over pitchers.
Bar (set before running): the selected configuration's coverage@3 exceeds the league default's by at least 0.05, with the lower end of the interval above 0.
The current default (N=4, h=2) is reported next to the selected one. If it trails the selected by more than 0.01 coverage, the default changes.

  python -m gameplan.usage_forecast --source mlb|milb --data <dir> --label <name> --out <dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
from collections import defaultdict

import numpy as np

from . import videocut as V

FAMS = ("FB", "BRK", "OFF")
POCKETS = [f"{h}-{s}" for h in ("low", "mid", "high") for s in ("in", "mid", "away")]
CELLS = [(f, p) for f in FAMS for p in POCKETS]
CELL = {c: i for i, c in enumerate(CELLS)}
CUTOFF = "2025-07-01"
MIN_START_PITCHES, MIN_PRIOR, MIN_SIDE = 45, 3, 15
GRID_N = (1, 2, 3, 5, 8, 99)
GRID_H = (1.0, 2.0, 4.0, None)
BAR = 0.05


def load_mlb(league_dir: pathlib.Path) -> list[dict]:
    out = []
    for f in sorted(league_dir.glob("*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            if r.get("game_type") not in (None, "", "R"):
                continue
            out.append(dict(pitcher=r["pitcher"], date=r["game_date"], game=r["game_pk"], stand=r["stand"], pitch_type=r["pitch_type"], px=r["plate_x"], pz=r["plate_z"],
                            sz_top=r["sz_top"], sz_bot=r["sz_bot"]))
    return out


def load_milb(cache: pathlib.Path) -> list[dict]:
    from . import milb_feed as MF
    return [dict(pitcher=str(p["pitcher"]), date=p["_date"], game=p["game_pk"], stand=p["stand"], pitch_type=p["pitch_type"], px=p["px"], pz=p["pz"], sz_top=p["sz_top"], sz_bot=p["sz_bot"])
            for p in MF.load(cache)]


def starts_table(pitches: list[dict]) -> dict:
    """{pitcher: [(date, game, counts[2][27], n)] sorted by date}; side 0 = L, 1 = R batters."""
    g = defaultdict(lambda: np.zeros((2, len(CELLS))))
    n = defaultdict(int)
    for p in pitches:
        n[(p["pitcher"], p["date"], p["game"])] += 1
        c = (V.pitch_family(p["pitch_type"]), V.pocket(dict(px=p["px"], pz=p["pz"], sz_top=p["sz_top"], sz_bot=p["sz_bot"], stand=p["stand"])))
        if c in CELL and p["stand"] in ("L", "R"):
            g[(p["pitcher"], p["date"], p["game"])][0 if p["stand"] == "L" else 1, CELL[c]] += 1
    out = defaultdict(list)
    for k, cnt in g.items():
        if n[k] >= MIN_START_PITCHES:
            out[k[0]].append((k[1], k[2], cnt, n[k]))
    return {p: sorted(v, key=lambda t: (t[0], t[1])) for p, v in out.items()}


def pooled(prior: list, N: int, h) -> np.ndarray:
    use = prior[::-1][:N]                                  # most recent first
    w = np.array([1.0 if h is None else 0.5 ** (k / h) for k in range(len(use))])
    return sum(wi * u[2] for wi, u in zip(w, use))


def logloss(counts, pred) -> float:
    p = (pred + 0.5) / (pred.sum() + 0.5 * len(pred))
    return float(-(counts * np.log(p)).sum() / counts.sum())


def cover(counts, cells) -> float:
    return float(counts[list(cells)].sum() / counts.sum())


def evaluate(starts: dict, league_top: dict) -> dict:
    cfgs = [(N, h) for N in GRID_N for h in GRID_H]
    train = {c: defaultdict(list) for c in cfgs}
    test = {c: defaultdict(list) for c in cfgs}
    base = defaultdict(list)
    orac = defaultdict(list)
    for pid, ss in starts.items():
        for i in range(MIN_PRIOR, len(ss)):
            date, game, cnt, _ = ss[i]
            is_test = date >= CUTOFF
            for side in (0, 1):
                if cnt[side].sum() < MIN_SIDE:
                    continue
                if is_test:
                    base[pid].append(cover(cnt[side], league_top[side]))
                    orac[pid].append(cover(cnt[side], np.argsort(-cnt[side])[:3]))
                for c in cfgs:
                    pr = pooled(ss[:i], *c)[side]
                    if not is_test:
                        train[c][pid].append(logloss(cnt[side], pr))
                    else:
                        test[c][pid].append(cover(cnt[side], np.argsort(-pr)[:3]))
    mean_over_pitchers = lambda d: {p: float(np.mean(v)) for p, v in d.items() if v}
    tr = {c: float(np.mean(list(mean_over_pitchers(train[c]).values()))) for c in cfgs if train[c]}
    best = min(tr, key=tr.get)
    return dict(cfgs=cfgs, train_ll=tr, best=best, test={c: mean_over_pitchers(test[c]) for c in cfgs}, base=mean_over_pitchers(base), oracle=mean_over_pitchers(orac))


def boot_diff(a: dict, b: dict, reps: int = 2000, seed: int = 5):
    ids = sorted(set(a) & set(b))
    d = np.array([a[i] - b[i] for i in ids])
    rng = np.random.default_rng(seed)
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(reps)]
    return float(d.mean()), [float(x) for x in np.percentile(bs, [2.5, 97.5])], len(ids)


def run(pitches: list[dict], label: str) -> dict:
    starts = starts_table(pitches)
    pre = [p for p in pitches if p["date"] < CUTOFF]
    league_top = {}
    for side, s in ((0, "L"), (1, "R")):
        c = np.zeros(len(CELLS))
        for p in pre:
            if p["stand"] == s:
                k = (V.pitch_family(p["pitch_type"]), V.pocket(dict(px=p["px"], pz=p["pz"], sz_top=p["sz_top"], sz_bot=p["sz_bot"], stand=s)))
                if k in CELL:
                    c[CELL[k]] += 1
        league_top[side] = list(np.argsort(-c)[:3])
    ev = evaluate(starts, league_top)
    best, default = ev["best"], (5, 2.0) if (5, 2.0) in ev["test"] else None
    default = (4, 2.0)
    res = dict(label=label, pitchers=len(starts), starts=sum(len(v) for v in starts.values()), best_config=[best[0], best[1]],
               league_top3=[[CELLS[i] for i in league_top[s]] for s in (0, 1)])
    for name, cfg in (("selected", best),):
        d, ci, n = boot_diff(ev["test"][cfg], ev["base"])
        res[name] = dict(cfg=list(cfg), coverage=round(float(np.mean(list(ev["test"][cfg].values()))), 4), lift_vs_league=round(d, 4), ci=[round(ci[0], 4), round(ci[1], 4)], pitchers=n,
                         passes_bar=bool(d >= BAR and ci[0] > 0))
    res["league_default_coverage"] = round(float(np.mean(list(ev["base"].values()))), 4)
    res["oracle_coverage"] = round(float(np.mean(list(ev["oracle"].values()))), 4)
    # the shipped default (N=4, h=2) is not on the grid; evaluate it directly
    dflt_starts = evaluate_cfg(starts, (4, 2.0))
    d, ci, n = boot_diff(dflt_starts, ev["base"])
    res["current_default_N4_h2"] = dict(coverage=round(float(np.mean(list(dflt_starts.values()))), 4), lift_vs_league=round(d, 4), ci=[round(ci[0], 4), round(ci[1], 4)])
    res["grid_test_coverage"] = {f"N{c[0]}_h{c[1]}": round(float(np.mean(list(v.values()))), 4) for c, v in ev["test"].items()}
    res["grid_train_logloss"] = {f"N{c[0]}_h{c[1]}": round(v, 4) for c, v in ev["train_ll"].items()}
    return res


def evaluate_cfg(starts: dict, cfg) -> dict:
    out = defaultdict(list)
    for pid, ss in starts.items():
        for i in range(MIN_PRIOR, len(ss)):
            if ss[i][0] < CUTOFF:
                continue
            for side in (0, 1):
                if ss[i][2][side].sum() >= MIN_SIDE:
                    out[pid].append(cover(ss[i][2][side], np.argsort(-pooled(ss[:i], *cfg)[side])[:3]))
    return {p: float(np.mean(v)) for p, v in out.items() if v}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mlb", "milb"], required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    pitches = load_mlb(pathlib.Path(a.data)) if a.source == "mlb" else load_milb(pathlib.Path(a.data))
    res = run(pitches, a.label)
    pathlib.Path(a.out, f"usage_forecast_{a.label}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if not k.startswith("grid")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
