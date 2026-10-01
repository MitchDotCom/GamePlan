"""Decision-relevance analysis: which inputs change calls, and do the three approach styles differ at all?

Part 1 (ablation). Held-out starter pitches, same protocol as validate_mlb (fit before the cutoff, score after).
For each variant of the engine we compare its calls (GO / NO_GO / no call) with the current default's:
  changed   share of the default's called pitches (GO or NO_GO) where the variant calls differently
  flipped   share where the variant calls the opposite action
  new/lost  calls the variant adds / drops
  S         separation against real run value (swing-minus-take gap in GO pitches minus the same in NO_GO pitches)
  dS        S of the variant minus S of the default, two-way (hitter and pitcher) cluster bootstrap
An input whose removal changes few calls and leaves S alone does not deserve more modelling. Nothing here is
adopted automatically.

Part 2 (path differentiation). For a sample of real hitter x starter x count matchups, how much do the VALUE,
CONTACT and HUNT styles (path_variants.py) differ, by share of the starter's pitches called differently and by
value if followed? If they rarely differ, "2 to 3 paths per count" collapses to one for most cells.

    python -m gameplan.relevance --b25 data/league --pitchers data/league --parts ablation,paths
"""
from __future__ import annotations

import argparse
import pathlib

import numpy as np

from .constants import value as _const
from .decision import SituationConfig, SituationPolicy, deltas_np, swing_se_np
from .shape import TTO_EFFECT_2025
from .stats import interval, two_way_draws
from .validate_mlb import OFF, _frames, _situation_delta, load_batters, load_start_keys
from .zone import CalledStrikeModel

GO = _const("GO_DELTA")
Z = _const("CONFIDENCE_Z")


def calls(delta: np.ndarray, se: np.ndarray, go: float = GO, z: float = Z) -> np.ndarray:
    """+1 GO, -1 NO_GO, 0 no call. A call needs the point estimate past the threshold and its z-sigma bound on the same side of zero."""
    out = np.zeros(len(delta), int)
    out[(delta >= go) & (delta - z * se >= 0)] = 1
    out[(delta <= -go) & (delta + z * se <= 0)] = -1
    return out


def _cat(frames, key):
    return np.concatenate([f[key] for f in frames])


def _delta(frames, p_key="p", counts="own", p_cs_key="p_cs", cv=None, shift=False):
    out = []
    for f in frames:
        p = f[p_key]
        w, x = p["whiff"], p["xw"]
        if shift:
            dw = np.array([TTO_EFFECT_2025[t][0] for t in f["tto"]])
            dx = np.array([TTO_EFFECT_2025[t][1] for t in f["tto"]])
            w, x = w + dw, x + dx
        b = np.zeros(f["n"], int) if counts == "blind" else f["balls"]
        s = np.zeros(f["n"], int) if counts == "blind" else f["strikes"]
        out.append(deltas_np(w, p["foul"], x, f[p_cs_key], b, s))
    return np.concatenate(out)


def _se(frames, p_key="p", league_only=False):
    out = []
    for f in frames:
        p = f[p_key]
        n_h = np.zeros(f["n"]) if league_only else f["n_h"]
        n_b = np.zeros(f["n"]) if league_only else f["n_bip_h"]
        out.append(swing_se_np(p["whiff"], p["foul"], p["xw"], f["balls"], f["strikes"], n_h, n_b, f["k"][0], f["k"][1]))
    return np.concatenate(out)


def separation(call, rv, swing, w):
    ok = ~np.isnan(rv)
    r = np.nan_to_num(rv)

    def gap(mask):
        a, b = mask & swing & ok, mask & ~swing & ok
        wa, wb = (w * a).sum(), (w * b).sum()
        return 0.0 if wa == 0 or wb == 0 else float((w * a * r).sum() / wa - (w * b * r).sum() / wb)
    return gap(call == 1) - gap(call == -1)


def ablation(events, cutoff, start_keys, n_boot=200):
    print(f"\n== Part 1: ablation, fit before {cutoff}, held-out starter pitches")
    league_train = [s for r in events.values() for s in r if s.swing and s.date < cutoff]
    zm = CalledStrikeModel([s for r in events.values() for s in r if not s.swing and s.date < cutoff])
    base = _frames(events, cutoff, start_keys, league_train, zm)
    rv, swing = _cat(base, "rv"), _cat(base, "swing")
    hid = np.concatenate([np.full(f["n"], k) for k, f in enumerate(base)])
    _, pidx = np.unique(_cat(base, "pitcher"), return_inverse=True)
    d0, se0 = _delta(base), _se(base)
    c0 = calls(d0, se0)
    print(f"  pitches {len(d0)}, default calls GO {int((c0 == 1).sum())} ({(c0 == 1).mean():.1%}), "
          f"NO_GO {int((c0 == -1).sum())} ({(c0 == -1).mean():.1%}), no call {(c0 == 0).mean():.1%}")

    variants = {}
    variants["no hitter-specific term (league model)"] = (_delta(base, "p_lg"), _se(base, "p_lg", True))
    variants["count-blind (every pitch scored as 0-0)"] = (_delta(base, counts="blind"), se0)
    variants["no confidence bounds (point estimate only)"] = (d0, np.zeros_like(se0))
    variants["TTO effect applied"] = (_delta(base, shift=True), se0)
    variants["zone surface by strikes only (no 3-ball surface)"] = (_delta(base, p_cs_key="p_cs_strikes"), se0)
    for name, thr in (("call threshold 0.01 (looser)", 0.01), ("call threshold 0.04 (stricter)", 0.04)):
        variants[name] = ("thr", thr)
    cfg = lambda pol: SituationConfig(pol, pol, pol, OFF, OFF)
    for name, pol in (("base-out MILD", SituationPolicy.MILD), ("base-out STRONG", SituationPolicy.STRONG)):
        variants[name] = (np.concatenate([_situation_delta(f, cfg(pol)) for f in base]), se0)
    for mode in ("shape", "typevelo", "type", "loc"):
        fr = _frames(events, cutoff, start_keys, league_train, zm, mode=mode)
        variants[f"contact model: {mode}" + (" (no count feature)" if mode == "shape" else "")] = (_delta(fr), _se(fr))

    S0 = lambda w: separation(c0, rv, swing, w)
    print(f"\n  {'variant':<52} {'changed':>8} {'flipped':>8} {'added':>7} {'dropped':>8} {'calls':>7}   dS vs default [95% CI]")
    print(f"  {'default':<52} {'':>8} {'':>8} {'':>7} {'':>8} {(c0 != 0).mean():>6.1%}   S = {S0(np.ones(len(rv))):+.4f}")
    called = c0 != 0
    for name, v in variants.items():
        c = calls(d0, se0, go=v[1]) if isinstance(v[0], str) else calls(v[0], v[1])
        chg = float((c[called] != c0[called]).mean())
        flip = float((c[called] == -c0[called]).mean())
        added = float(((c != 0) & ~called).sum() / max(called.sum(), 1))
        dropped = float(((c == 0) & called).sum() / max(called.sum(), 1))
        stat = lambda w, c=c: separation(c, rv, swing, w) - S0(w)
        point, draws = two_way_draws(hid, pidx, stat, n_boot)
        pt, lo, hi = interval(point, draws)
        print(f"  {name:<52} {chg:>8.1%} {flip:>8.1%} {added:>7.1%} {dropped:>8.1%} {(c != 0).mean():>6.1%}   {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    print("  changed/flipped/added/dropped are shares of the default's called pitches.")


def paths(league_dir, cutoff, n_games=25, seed=11):
    """Part 2. Matchups come from real games after the cutoff; everything is fit before it."""
    import csv
    import glob

    from .mockup import Engine, load_events, load_pitcher_rows
    from .path_variants import all_styles, call_difference
    from .savant import parse_swings

    print(f"\n== Part 2: do the styles differ? fit before {cutoff}, {n_games} real starter games after it")
    events = load_events(league_dir, cutoff)
    files = [f for f in sorted(glob.glob(str(pathlib.Path(league_dir) / "*.csv"))) if pathlib.Path(f).stem >= cutoff]
    rng = np.random.default_rng(seed)
    games = []                                    # (date, game_pk, starter)
    for f in files:
        seen = {}
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            if r["inning"] == "1":
                seen.setdefault((r["game_pk"], r["pitcher"]), pathlib.Path(f).stem)
        games += [(d, g, p) for (g, p), d in seen.items()]
    rng.shuffle(games)
    base = Engine(events, [], cutoff, "0")
    counts = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (3, 1), (1, 2)]
    rec = {c: {"vc": [], "vh": [], "dv_c": [], "dv_h": [], "go_share": []} for c in counts}
    done = 0
    for date, game, starter in games:
        if done >= n_games:
            break
        rows = load_pitcher_rows(league_dir, starter, cutoff)
        if len({p.game_pk for p in rows}) < 8:
            continue
        gtxt = open(pathlib.Path(league_dir) / f"{date}.csv", encoding="utf-8-sig").read()
        grows = [s for s in parse_swings(gtxt, include_takes=True) if s.game_pk == game and s.pitcher == starter]
        lineup, stands = [], {}
        for s in sorted(grows, key=lambda s: (s.at_bat, s.pitch_no)):
            if s.batter not in lineup:
                lineup.append(s.batter)
        for h in lineup[:9]:
            st = [s.stand for s in grows if s.batter == h and s.stand]
            stands[h] = max(set(st), key=st.count) if st else "R"
        eng = base.retarget(rows, starter)
        used = 0
        for h in lineup[:9]:
            if len([s for s in eng.by_hitter[h] if s.swing]) < 300:
                continue
            hit = eng.hitter(h)
            for b, s in counts:
                snap = eng.snapshot(h, 1, b, s, stands[h], hit)
                sm = all_styles(snap, eng.locations, eng.rate(h), stands[h])
                rec[(b, s)]["vc"].append(call_difference(snap, "VALUE", "CONTACT", eng.locations, stands[h]))
                rec[(b, s)]["vh"].append(call_difference(snap, "VALUE", "HUNT", eng.locations, stands[h]))
                rec[(b, s)]["dv_c"].append(sm["CONTACT"].value_per_100 - sm["VALUE"].value_per_100)
                rec[(b, s)]["dv_h"].append(sm["HUNT"].value_per_100 - sm["VALUE"].value_per_100)
                rec[(b, s)]["go_share"].append(sm["VALUE"].swing_share)
            used += 1
        done += 1
        print(f"  game {done}/{n_games} {date} starter {starter}: {used} hitters")
    q = lambda a, p: float(np.percentile(a, p)) if len(a) else float("nan")
    print(f"\n  {'count':<6}{'n':>5}  {'CONTACT differs: median [Q1,Q3]':<34}{'>=5%':>6}{'>=20%':>7}   {'HUNT differs: median [Q1,Q3]':<32}{'>=5%':>6}{'>=20%':>7}   "
          f"{'value gap CONTACT / HUNT (runs per 100, median)':<48}{'VALUE swing share':>18}")
    for c, d in rec.items():
        vc, vh = np.array(d["vc"]), np.array(d["vh"])
        print(f"  {c[0]}-{c[1]:<4}{len(vc):>5}  {q(vc, 50):>7.1%} [{q(vc, 25):.1%}, {q(vc, 75):.1%}]".ljust(54)
              + f"{(vc >= .05).mean():>6.0%}{(vc >= .2).mean():>7.0%}   {q(vh, 50):>7.1%} [{q(vh, 25):.1%}, {q(vh, 75):.1%}]".ljust(36)
              + f"{(vh >= .05).mean():>6.0%}{(vh >= .2).mean():>7.0%}   {q(d['dv_c'], 50):+.2f} / {q(d['dv_h'], 50):+.2f}".ljust(52)
              + f"{q(d['go_share'], 50):>12.1%}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    ap.add_argument("--parts", default="ablation,paths")
    ap.add_argument("--n-games", type=int, default=25)
    a = ap.parse_args(argv)
    parts = set(a.parts.split(","))
    if "ablation" in parts:
        ablation(load_batters(a.b25), a.cutoff, load_start_keys(a.pitchers))
    if "paths" in parts:
        paths(a.b25, a.cutoff, a.n_games)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
