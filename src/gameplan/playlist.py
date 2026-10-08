"""Hitter-specific playlists against a starter, from pooled recent starts (MLB public data).

  starts   : the starter's last N starts before a date (statsapi game log), feeds cached on disk so reruns and growth are cheap
  pooled   : every pitch from those starts, tagged with its age in starts (0 = most recent)
  playlists: named generators that turn (pooled pitches, hitter) into a list of (family, pocket) shapes; clips come from those shapes

Generators registered in GENERATORS:
  usage         the starter's most-used shapes vs this hitter's side, recent starts weighted more. The validated rule (V2: nothing beat it).
  hitter_cost   among shapes the starter really throws, the ones where this hitter's own raw results cost him most (Statcast delta_run_exp,
                shrunk toward his overall rate, several seasons, older seasons weighted less). Descriptive: on 2022-2025 it did not beat usage (V2).
  ride          his fastball-ride slope (whiff vs vertical break, Gate 0b, confirmed 4 of 4 seasons) applied to the starter's fastballs: the ones
                at the ride extreme where his whiff risk is highest. Needs a slope whose interval excludes zero, else it says so and returns nothing.
  run           same for breaking-ball run (horizontal break, the strongest confirmed trait).
Add a generator by writing fn(rows, hitter, n) -> [(family, pocket), ...] and registering it.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
from collections import Counter, defaultdict

import numpy as np

from . import savant
from . import videocut as V
from .traits_test import _fit_logit as ridge_logit

STATSAPI = "https://statsapi.mlb.com/api/v1"
HALF_LIFE = 2.0     # starts; a start two outings ago counts half
K_SHRINK = 40       # pitches; same pull toward the hitter's overall rate used in V5
MIN_SHARE = 0.05    # a shape must be at least this share of the starter's weighted pitches to be offered
SEASON_HALF_LIFE = 1.0   # seasons; last season counts half as much as this one
K_SLOPE = 100.0     # ridge strength on his ride/run slope, same as Gate 0b
MIN_SWINGS = 150    # his swings in the family needed before a slope is reported
BOOT = 200


def recent_starts(pitcher_id: int, season: int, before: str, n: int = 5) -> list[tuple]:
    """[(date, game_pk)] of the pitcher's last n starts strictly before `before` (YYYY-MM-DD), most recent first."""
    d = json.loads(V._get(f"{STATSAPI}/people/{pitcher_id}/stats?stats=gameLog&group=pitching&season={season}"))
    splits = d["stats"][0]["splits"] if d.get("stats") else []
    st = [(s["date"], s["game"]["gamePk"]) for s in splits if s["stat"].get("gamesStarted") == 1 and s["date"] < before]
    return sorted(st, reverse=True)[:n]


def pooled(pitcher_id: int, starts: list[tuple], cache: pathlib.Path) -> list[dict]:
    """All pitches by this pitcher across the starts. Each game feed is cached as JSON, so only new games hit the network."""
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for age, (date, pk) in enumerate(starts):
        f = cache / f"{pk}.json"
        if not f.exists():
            f.write_text(json.dumps(V.game_pitches(pk)))
        for p in json.loads(f.read_text()):
            if p.get("type") == "pitch" and p.get("pitcher") == pitcher_id:
                out.append(dict(p, _age=age, _date=date, game_pk=str(pk)))
    return out


def _weight(p: dict) -> float:
    return 0.5 ** (p["_age"] / HALF_LIFE)


def _shape(p: dict):
    pk = V.pocket(p)
    return (V.pitch_family(p.get("pitch_type", "")), pk) if pk else None


def usage(rows: list[dict], hitter: dict, n: int = 3) -> list[tuple]:
    c = Counter()
    for p in rows:
        if p.get("stand") == hitter["stand"] and _shape(p):
            c[_shape(p)] += _weight(p)
    return [k for k, _ in c.most_common(n)]


BUCKETS = ("first", "ahead", "even", "behind", "two_strike")
MIN_BUCKET = 25     # pitches to this side in a count bucket before a count-specific list is offered

EVIDENCE = {
    "usage": "validated rule (V2: nothing beat it), MLB 2022-2025",
    "hitter_cost": "descriptive; did not beat usage in V2",
    "ride": "thin: split-half r 0.63 but year over year r 0.21, interval includes zero (2026-10-08, MLB)",
    "run": "reliable: split-half r 0.75, year over year r 0.46 (2026-10-08, MLB)",
}
COUNT_EVIDENCE = "count-specific lists are descriptive, not validated"


def count_bucket(p: dict):
    try:
        b, k = int(p["balls"]), int(p["strikes"])
    except (KeyError, TypeError, ValueError):
        return None
    if k == 2:
        return "two_strike"
    if b == 0 and k == 0:
        return "first"
    return "ahead" if b > k else "even" if b == k else "behind"


def read_rows(csv_text: str, season: int) -> list[dict]:
    return [dict(r, _season=season) for r in csv.DictReader(io.StringIO(csv_text))]


def hitter_history(hitter_id: int, seasons: list[int], cache: pathlib.Path) -> list[dict]:
    """His Statcast pitch rows for each season (one cached CSV per season; the current season is refetched since it grows)."""
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for i, yr in enumerate(sorted(seasons)):
        f = cache / f"{hitter_id}_{yr}.csv"
        if not f.exists() or yr == max(seasons):
            f.write_text(savant.fetch_csv(savant.build_url(hitter_id, yr)))
        out += read_rows(f.read_text(), yr)
    return out


def _sw(r: dict, latest: int) -> float:
    return 0.5 ** ((latest - r["_season"]) / SEASON_HALF_LIFE)


def hitter_cost(rows: list[dict], hitter: dict, n: int = 3) -> list[tuple]:
    """hitter['rows'] is his pitch history (hitter_history); several seasons, each older season weighted less."""
    total = sum(_weight(p) for p in rows if p.get("stand") == hitter["stand"] and _shape(p))
    c = Counter()
    for p in rows:
        if p.get("stand") == hitter["stand"] and _shape(p):
            c[_shape(p)] += _weight(p)
    offered = {k for k, w in c.items() if total and w / total >= MIN_SHARE}
    hand = rows[0].get("p_throws") if rows else None
    hist = hitter["rows"]
    latest = max((r["_season"] for r in hist), default=0)
    cost, cnt = defaultdict(float), defaultdict(float)
    allc = alln = 0.0
    for r in hist:
        if hand and r.get("p_throws") != hand:
            continue
        try:
            v = -float(r["delta_run_exp"])
            q = dict(px=r["plate_x"], pz=r["plate_z"], sz_top=r["sz_top"], sz_bot=r["sz_bot"], stand=r["stand"])
            fam = V.pitch_family(r["pitch_type"])
        except (KeyError, ValueError, TypeError):
            continue
        w = _sw(r, latest)
        pk = V.pocket(q)
        allc += w * v
        alln += w
        if pk:
            cost[(fam, pk)] += w * v
            cnt[(fam, pk)] += w
    mu = allc / alln if alln else 0.0
    score = {k: (cost[k] + K_SHRINK * mu) / (cnt[k] + K_SHRINK) for k in offered}
    return sorted(score, key=lambda k: -score[k])[:n]


# ---------------------------------------------------------------- ride and run (Gate 0b traits)

WHIFF = savant.WHIFF_DESCRIPTIONS | {"foul_tip"}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def starter_move(p: dict):
    """(ride_in, run_in) of a pooled feed pitch in inches, same definitions as the study: ride = induced vertical break (pfx_z * 12),
    run = the study's horizontal break (api_break_x_batter_in * 12). Despite its name, on this column an RHP sinker vs a left-handed batter is negative and his slider positive, so positive = break away from the batter, negative = toward him (checked on Singer's pitches vs Nootbaar). The feed's pfxX has the opposite sign to Statcast's pfx_x."""
    z, x = _f(p.get("pfxZ")), _f(p.get("pfxX"))
    if z is None or x is None or p.get("stand") not in ("L", "R"):
        return None, None
    return z * 12.0, (x if p["stand"] == "R" else -x) * 12.0


def trait_slope(hist: list[dict], family: str, trait: str, seed: int = 7, min_swings: int = MIN_SWINGS, boot: int = BOOT) -> dict:
    """His whiff-per-swing slope on ride (family FB) or run (family BRK), per sd of the feature, controlling for location, speed and two strikes,
    ridge-shrunk toward zero (K=100) and bootstrapped over his swings. Simplified from Gate 0b (no league slope or pitcher intercepts), so read it as
    a direction and a size, not the validated estimate itself."""
    key = "pfx_z" if trait == "ride" else "api_break_x_batter_in"
    X, y = [], []
    for r in hist:
        if V.pitch_family(r.get("pitch_type", "")) != family or r.get("description") not in savant.SWING_DESCRIPTIONS | {"foul_tip"}:
            continue
        v = [_f(r.get(k)) for k in (key, "plate_x", "plate_z", "release_speed")]
        if None in v:
            continue
        X.append(v + [1.0 if r.get("strikes") == "2" else 0.0])
        y.append(1.0 if r["description"] in WHIFF else 0.0)
    n = len(y)
    out = dict(n=n, trait=trait, family=family)
    if n < min_swings:
        return dict(out, ok=False, why=f"only {n} swings (need {min_swings})")
    X, y = np.array(X), np.array(y)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    Z[:, 4] = X[:, 4]
    Z2 = np.column_stack([Z[:, 0], Z[:, 1], Z[:, 2], Z[:, 1] ** 2, Z[:, 2] ** 2, Z[:, 3], Z[:, 4]])
    off = np.log(y.mean() / (1 - y.mean())) if 0 < y.mean() < 1 else 0.0
    slope = ridge_logit(Z2, y, np.full(n, off), lam=K_SLOPE)[0]
    if not boot:
        return dict(out, ok=True, slope=float(slope), mean=float(mu[0]), sd=float(sd[0]), whiff_rate=float(y.mean()))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(boot):
        i = rng.integers(0, n, n)
        boots.append(ridge_logit(Z2[i], y[i], np.full(n, off), lam=K_SLOPE)[0])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return dict(out, ok=True, slope=float(slope), lo=float(lo), hi=float(hi), clear=bool(lo > 0 or hi < 0),
                mean=float(mu[0]), sd=float(sd[0]), whiff_rate=float(y.mean()))


def _trait_pitches(rows: list[dict], hitter: dict, trait: str, n: int):
    fam = "FB" if trait == "ride" else "BRK"
    t = trait_slope(hitter["rows"], fam, trait)
    if not t["ok"] or not t["clear"]:
        return t, []
    # feature on the same scale as the slope (feet); pooled pitches are in inches
    pool = [(p, starter_move(p)[0 if trait == "ride" else 1]) for p in rows
            if p.get("stand") == hitter["stand"] and V.pitch_family(p.get("pitch_type", "")) == fam]
    pool = [(p, m / 12.0) for p, m in pool if m is not None]
    if not pool:
        return t, []
    z = [((m - t["mean"]) / t["sd"], p) for p, m in pool]
    z.sort(key=lambda a: -a[0] if t["slope"] > 0 else a[0])     # most whiff-prone end first
    return t, [p for _, p in z[:max(n, 1)]]


def _gen(trait):
    def fn(rows, hitter, n=3):
        t, ps = _trait_pitches(rows, hitter, trait, n)
        hitter.setdefault("notes", {})[trait] = t
        return ps
    fn.returns_pitches = True
    return fn


GENERATORS = {"usage": usage, "hitter_cost": hitter_cost, "ride": _gen("ride"), "run": _gen("run")}


def playlist(name: str, rows: list[dict], hitter: dict, n: int = 3, limit: int = 8, seed: int = 1, bucket: str | None = None) -> dict:
    """Shapes from the named generator and the pooled pitches that fall in them (this hitter's side), most recent starts first within a fixed-seed shuffle.
    bucket restricts the pool to one count state; if it holds fewer than MIN_BUCKET pitches to his side the list is empty and says why."""
    if bucket:
        rows = [p for p in rows if count_bucket(p) == bucket]
        side = sum(1 for p in rows if p.get("stand") == hitter["stand"])
        if side < MIN_BUCKET:
            return dict(name=name, hitter=hitter.get("name"), shapes=[], pitches=[], pool=len(rows), starts=0, bucket=bucket, why=f"only {side} pitches to {hitter['stand']}HH in this count state (need {MIN_BUCKET})", evidence=EVIDENCE[name] + "; " + COUNT_EVIDENCE)
    out = _playlist(name, rows, hitter, n, limit, seed)
    out["evidence"] = EVIDENCE[name] + ("; " + COUNT_EVIDENCE if bucket else "")
    if bucket:
        out["bucket"] = bucket
    return out


def _playlist(name: str, rows: list[dict], hitter: dict, n: int, limit: int, seed: int) -> dict:
    gen = GENERATORS[name]
    if getattr(gen, "returns_pitches", False):
        top = gen(rows, hitter, max(limit, n))
        top = [dict(p, type="pitch") for p in top]
        return dict(name=name, hitter=hitter.get("name"), shapes=[], pitches=top[:limit], pool=len(rows), starts=len({p["game_pk"] for p in rows}),
                    note=hitter.get("notes", {}).get(name))
    shapes = gen(rows, hitter, n)
    sel = V.select([dict(p, type="pitch") for p in rows], stand=hitter["stand"], shapes=tuple(shapes), limit=10 ** 6, seed=seed)
    sel.sort(key=lambda p: p["_age"])
    return dict(name=name, hitter=hitter.get("name"), shapes=shapes, pitches=sel[:limit], pool=len(rows), starts=len({p["game_pk"] for p in rows}))


def main(argv=None) -> int:
    import argparse
    from . import mlb_demo, savant
    ap = argparse.ArgumentParser(description="Hitter playlist vs a starter from pooled recent starts")
    ap.add_argument("--pitcher-id", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--before", required=True, help="YYYY-MM-DD; only starts before this date are pooled")
    ap.add_argument("--starts", type=int, default=5)
    ap.add_argument("--hitter-id", type=int, required=True)
    ap.add_argument("--hitter-seasons", type=int, default=3, help="seasons of his history, ending with --season")
    ap.add_argument("--hitter-name", default=None)
    ap.add_argument("--stand", choices=["L", "R"], required=True)
    ap.add_argument("--name", choices=sorted(GENERATORS), default="usage")
    ap.add_argument("--n-shapes", type=int, default=3)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    work = pathlib.Path(a.work)
    starts = recent_starts(a.pitcher_id, a.season, a.before, a.starts)
    rows = pooled(a.pitcher_id, starts, work / "feeds")
    hitter = dict(stand=a.stand, name=a.hitter_name or str(a.hitter_id))
    if a.name != "usage":
        hitter["rows"] = hitter_history(a.hitter_id, list(range(a.season - a.hitter_seasons + 1, a.season + 1)), work / "hitters")
    pl = playlist(a.name, rows, hitter, a.n_shapes, a.limit)
    print(f"{pl['name']} for {pl['hitter']} ({a.stand}) from {pl['starts']} starts, {pl['pool']} pitches: shapes {pl['shapes']}; {len(pl['pitches'])} candidate pitches")
    if pl.get("note"):
        print("trait:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in pl["note"].items()})
    if not pl["pitches"]:
        print("no playlist: nothing met its rule (see trait line); not falling back silently")
        return 1
    mlb_demo.build_rows(pl["pitches"], work, pathlib.Path(a.out), a.limit,
                        title=f"Go / No-Go: {a.hitter_name or a.hitter_id} ({a.stand}), {a.name} playlist, last {pl['starts']} starts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
