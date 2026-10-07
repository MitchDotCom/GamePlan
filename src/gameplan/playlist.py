"""Hitter-specific playlists against a starter, from pooled recent starts (MLB public data).

  starts   : the starter's last N starts before a date (statsapi game log), feeds cached on disk so reruns and growth are cheap
  pooled   : every pitch from those starts, tagged with its age in starts (0 = most recent)
  playlists: named generators that turn (pooled pitches, hitter) into a list of (family, pocket) shapes; clips come from those shapes

Generators registered in GENERATORS:
  usage         the starter's most-used shapes vs this hitter's side, recent starts weighted more. The validated rule (V2: nothing beat it).
  hitter_cost   among shapes the starter really throws, the ones where this hitter's own raw results cost him most (Statcast delta_run_exp,
                shrunk toward his overall rate). Descriptive: on 2022-2025 it did not beat usage (V2), so it is a second view, not a better pick.
Add a generator by writing fn(rows, hitter, n) -> [(family, pocket), ...] and registering it.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
from collections import Counter, defaultdict

from . import videocut as V

STATSAPI = "https://statsapi.mlb.com/api/v1"
HALF_LIFE = 2.0     # starts; a start two outings ago counts half
K_SHRINK = 40       # pitches; same pull toward the hitter's overall rate used in V5
MIN_SHARE = 0.05    # a shape must be at least this share of the starter's weighted pitches to be offered


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


def hitter_cost(rows: list[dict], hitter: dict, n: int = 3) -> list[tuple]:
    """hitter['csv'] is that hitter's Statcast pitch CSV text (savant.build_url / fetch_csv). Needs hitter['stand']."""
    total = sum(_weight(p) for p in rows if p.get("stand") == hitter["stand"] and _shape(p))
    c = Counter()
    for p in rows:
        if p.get("stand") == hitter["stand"] and _shape(p):
            c[_shape(p)] += _weight(p)
    offered = {k for k, w in c.items() if total and w / total >= MIN_SHARE}
    hand = rows[0].get("p_throws") if rows else None
    cost, cnt = defaultdict(float), defaultdict(int)
    allc = alln = 0
    for r in csv.DictReader(io.StringIO(hitter["csv"])):
        if hand and r.get("p_throws") != hand:
            continue
        try:
            v = -float(r["delta_run_exp"])
            q = dict(px=r["plate_x"], pz=r["plate_z"], sz_top=r["sz_top"], sz_bot=r["sz_bot"], stand=r["stand"])
            fam = V.pitch_family(r["pitch_type"])
        except (KeyError, ValueError, TypeError):
            continue
        pk = V.pocket(q)
        allc += v
        alln += 1
        if pk:
            cost[(fam, pk)] += v
            cnt[(fam, pk)] += 1
    mu = allc / alln if alln else 0.0
    score = {k: (cost[k] + K_SHRINK * mu) / (cnt[k] + K_SHRINK) for k in offered}
    return sorted(score, key=lambda k: -score[k])[:n]


GENERATORS = {"usage": usage, "hitter_cost": hitter_cost}


def playlist(name: str, rows: list[dict], hitter: dict, n: int = 3, limit: int = 8, seed: int = 1) -> dict:
    """Shapes from the named generator and the pooled pitches that fall in them (this hitter's side), most recent starts first within a fixed-seed shuffle."""
    shapes = GENERATORS[name](rows, hitter, n)
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
    if a.name == "hitter_cost":
        hitter["csv"] = savant.fetch_csv(savant.build_url(a.hitter_id, a.season))
    pl = playlist(a.name, rows, hitter, a.n_shapes, a.limit)
    print(f"{pl['name']} for {pl['hitter']} ({a.stand}) from {pl['starts']} starts, {pl['pool']} pitches: shapes {pl['shapes']}; {len(pl['pitches'])} candidate pitches")
    mlb_demo.build_rows(pl["pitches"], work, pathlib.Path(a.out), a.limit,
                        title=f"Go / No-Go: {a.hitter_name or a.hitter_id} ({a.stand}), {a.name} playlist, last {pl['starts']} starts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
