"""Path generator v1 (plan WS4): 1 to 3 approach paths per hitter, scored over the whole plate appearance.

A path is a policy: a swing probability for every pitch type and cell in every count. The styles come from path_variants.style_cells
(VALUE, CONTACT, HUNT); a GO cell is swung at (1), a NO_GO cell is taken (0), and a cell with no call keeps the hitter's own tendency
(SwingRateModel). The baseline is his tendency everywhere. pa_value.solve turns each policy into the expected wOBA of a plate appearance
from 0-0, so a path's value includes what the swing does to the count that follows.

Uncertainty. Each cell's swing value carries the standard error the plan already computes (cell["se"]). Monte Carlo: add N(0, se) to the
cell's xwOBA on contact, solve every policy on the same draw, and keep the paired differences. The SD of a difference is the spread of
that difference over the draws. This puts all of the cell uncertainty on contact quality, which is an approximation (CHOICE, stated on screen).

Which paths are shown, per count (all thresholds are CHOICES for a coach to set, not fit):
  VALUE is always shown. HUNT is never shown while HUNT_ENABLED is False (no anticipation term in the model yet).
  Another style is shown only if (a) it is viable: its mean plate-appearance value is within VIABLE_TOL runs per 100 plate appearances of VALUE, and
  (b) its calls differ from every shown path on at least MIN_DIFF of the starter's pitches in that count.
Otherwise the count shows one path and says so.

    python -m gameplan.paths --league data/league --date 2025-09-07 --game 776415 --away BOS --home ARI"""
from __future__ import annotations

import argparse

import numpy as np

from .constants import value as _const
from .decision import DEFAULT, GO_DELTA, NO_GO_DELTA
from .pa_value import solve
from .path_variants import STYLES, style_cells

COUNTS = [(b, s) for s in range(3) for b in range(4)]
DRAWS = 100
VIABLE_TOL = 1.5          # runs per 100 plate appearances below VALUE that still counts as a viable alternative (CHOICE)
MIN_DIFF = 0.10           # share of the starter's pitches where calls must differ to be a different path (CHOICE)
HUNT_ENABLED = False      # plan WS4.1: HUNT ships only if the pre-registered anticipation test passes; until then it is scored but never shown
SCALE = _const("WOBA_SCALE_2025")


def _items(eng, h, tto, b, s, stand, hit):
    return items_from_snap(eng, h, eng.snapshot(h, tto, b, s, stand, hit), s, stand)


def items_from_snap(eng, h, snap, s, stand):
    """Arrays over every (pitch type, cell) of one count: weight, his swing tendency, outcome rates, called-strike share, standard error,
    and the swing probability each style implies."""
    cells = {st: style_cells(snap, st) for st in STYLES}
    locs, rate = eng.locations, eng.rate(h)
    xs = np.array([c[2] for c in locs.cells])
    zs = np.array([c[3] for c in locs.cells])
    cols = {k: [] for k in ("m", "psw", "whiff", "foul", "xw", "pcs", "se")}
    cls = {st: [] for st in STYLES}
    keys = []
    for pt, a in snap.arsenal.items():
        mass = locs.mass(pt, stand, min(s, 2)) * a["usage"]
        psw = rate.p(xs, zs, pt, s)
        for n, (i, j, _, _) in enumerate(locs.cells):
            c = snap.cells.get(f"{pt}|{i}|{j}")
            if c is None or mass[n] <= 0:
                continue
            keys.append(f"{pt}|{i}|{j}")
            cols["m"].append(mass[n])
            cols["psw"].append(psw[n])
            cols["whiff"].append(c["whiff"])
            cols["foul"].append(c["foul"])
            cols["xw"].append(c["xw"])
            cols["pcs"].append(c["p_cs"])
            cols["se"].append(c["se"])
            for st in STYLES:
                cls[st].append(cells[st][f"{pt}|{i}|{j}"]["cls"])
    out = {k: np.array(v, float) for k, v in cols.items()}
    out["keys"] = keys
    out["m"] = out["m"] / out["m"].sum()
    out["ps"] = {"BASE": out["psw"]}
    for st in STYLES:
        c = np.array(cls[st])
        out["ps"][st] = np.where(c == "GO", 1.0, np.where(c == "NO_GO", 0.0, out["psw"]))
    return out


def _continuation(V, b, s):
    return (0.0 if s + 1 >= 3 else V[(b, s + 1)], DEFAULT.walk if b + 1 >= 4 else V[(b + 1, s)], V[(b, s)] if s >= 2 else V[(b, s + 1)])


def _solve_ps(items, ps):
    return solve({c: {"m": it["m"], "ps": ps[c], "whiff": it["whiff"], "foul": it["foul"], "xw": it["xw"], "pcs": it["pcs"]}
                  for c, it in items.items()})


def full_policy(items: dict, iters: int = 10) -> dict:
    """The FULL path: decide every cell, thin evidence included. Step 1: the plate-appearance optimum under the model's own estimates
    (swing wherever swinging beats taking, valued with the optimal rest of the plate appearance; policy iteration, converges in 2 or 3
    rounds). Step 2: the displayed calls, using that continuation, with the plan's GO_DELTA / NO_GO_DELTA margins but no confidence bound
    (z = 0). Cells inside the margins keep his tendency. Returns {(b, s): array of "GO" / "NO_GO" / "CONDITIONAL"}.
    Why a separate path: with the confidence bound (z = 1.28) the same iteration does no better than the per-pitch plan; the bound is what
    keeps thin-evidence cells at "no call" and costs about a run per 100 plate appearances in the model (docs/paths_evidence.txt)."""
    cur = {c: it["ps"]["VALUE"].copy() for c, it in items.items()}
    for _ in range(iters):
        V = _solve_ps(items, cur)
        new = {}
        for (b, s), it in items.items():
            vs, vb, vf = _continuation(V, b, s)
            bip = np.maximum(1.0 - it["whiff"] - it["foul"], 0.0)
            d = (it["whiff"] * vs + it["foul"] * vf + bip * it["xw"]) - (it["pcs"] * vs + (1.0 - it["pcs"]) * vb)
            new[(b, s)] = (d > 0).astype(float)
        if all(np.array_equal(new[c], cur[c]) for c in items):
            break
        cur = new
    out = {}
    for (b, s), it in items.items():
        vs, vb, vf = _continuation(V, b, s)
        bip = np.maximum(1.0 - it["whiff"] - it["foul"], 0.0)
        d = (it["whiff"] * vs + it["foul"] * vf + bip * it["xw"]) - (it["pcs"] * vs + (1.0 - it["pcs"]) * vb)
        out[(b, s)] = np.where(d >= GO_DELTA, "GO", np.where(d <= NO_GO_DELTA, "NO_GO", "CONDITIONAL"))
    return out


def path_report(eng, h: str, tto: int, stand: str, hit, draws: int = DRAWS, seed: int = 3) -> dict:
    items = {c: _items(eng, h, tto, c[0], c[1], stand, hit) for c in COUNTS}
    rng = np.random.default_rng(seed)
    names = ("BASE",) + tuple(STYLES)
    vals = {n: [] for n in names}
    for d in range(draws + 1):
        noise = {c: (np.zeros_like(it["se"]) if d == 0 else rng.normal(0.0, it["se"])) for c, it in items.items()}   # draw 0 = point estimate
        for n in names:
            menus = {c: {"m": it["m"], "ps": it["ps"][n], "whiff": it["whiff"], "foul": it["foul"],
                         "xw": np.clip(it["xw"] + noise[c], 0.0, 2.0), "pcs": it["pcs"]} for c, it in items.items()}
            vals[n].append(solve(menus)[(0, 0)])
    v = {n: np.array(x) for n, x in vals.items()}
    to_runs = lambda x: x / SCALE * 100.0                                     # wOBA per PA -> runs per 100 PA
    paths = {}
    for st in STYLES:
        dv = to_runs(v[st][1:] - v["VALUE"][1:])
        db = to_runs(v[st][1:] - v["BASE"][1:])
        paths[st] = {"vs_tendency": round(float(to_runs(v[st][0] - v["BASE"][0])), 2), "vs_tendency_sd": round(float(db.std()), 2),
                     "vs_value": round(float(to_runs(v[st][0] - v["VALUE"][0])), 2), "vs_value_sd": round(float(dv.std()), 2),
                     "viable": bool(to_runs(v[st][0] - v["VALUE"][0]) >= -VIABLE_TOL)}
    diff, shown = {}, {}
    for c, it in items.items():
        key = f"{c[0]}-{c[1]}"
        diff[key] = {st: round(float((it["m"] * np.abs(it["ps"]["VALUE"] - it["ps"][st])).sum()), 3) for st in STYLES if st != "VALUE"}
        keep = ["VALUE"]
        for st in STYLES:
            if st == "VALUE" or not paths[st]["viable"] or (st == "HUNT" and not HUNT_ENABLED):
                continue
            if all(float((it["m"] * np.abs(it["ps"][k] - it["ps"][st])).sum()) >= MIN_DIFF for k in keep):
                keep.append(st)
        shown[key] = keep
    return {"paths": paths, "call_diff": diff, "shown": shown}


def main(argv=None) -> int:
    from collections import Counter
    from .game import load_game
    from .mockup import Engine, load_events, load_pitcher_rows
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--game", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--tto", type=int, default=1)
    a = ap.parse_args(argv)
    rows = load_game(a.league, a.date, a.game)
    base = Engine(load_events(a.league, a.date), [], a.date, "0")
    n_one = n_cells = 0
    for half in ("Top", "Bot"):
        starter = next(r for r in rows if r["inning_topbot"] == half)["pitcher"]
        faced = []
        for r in rows:
            if r["inning_topbot"] == half and r["pitcher"] == starter and r["batter"] not in faced:
                faced.append(r["batter"])
        eng = base.retarget(load_pitcher_rows(a.league, starter, a.date), starter)
        for h in faced:
            st = [r["stand"] for r in rows if r["batter"] == h and r["pitcher"] == starter and r["stand"] in ("R", "L")]
            stand = Counter(st).most_common(1)[0][0] if st else "R"
            rep = path_report(eng, h, a.tto, stand, eng.hitter(h))
            p = rep["paths"]
            one = sum(len(v) == 1 for v in rep["shown"].values())
            n_one += one
            n_cells += len(rep["shown"])
            print(f"{half} {h}: " + "; ".join(f"{s} vs value {p[s]['vs_value']:+.2f}±{p[s]['vs_value_sd']:.2f}{'' if p[s]['viable'] else ' (not viable)'}" for s in STYLES if s != "VALUE")
                  + f"; one path in {one} of 12 counts", flush=True)
    print(f"\ncounts showing one path: {n_one} of {n_cells} ({n_one / max(n_cells, 1):.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
