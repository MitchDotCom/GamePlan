"""The lineup plan for a real minor-league starter, built only from cached public minor-league feeds (gameplan.milb_feed).

  python -m gameplan.milb_lineup --cache <dir> --label AAA-IL --out <dir> [--pitcher-id N] [--starts 4] [--min-starts 8]

Picks a starter (the one with the most starts in the cache unless --pitcher-id is given), treats his LAST cached start as the game being planned for, pools his previous starts
(the validated usage rule, recency half-life as in playlist.py), takes the lineup from the batters who faced him in that last start, and builds for each hitter the lists that can be
built here: usage, ride and run. Hitter history is the same league's earlier games only (no cross-level history), and nothing from the planned game or later is used.
Not built here: hitter_cost (needs Statcast run values, which minor-league feeds do not carry) and clips (no minor-league clips exist).
"""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter, defaultdict

from . import milb_feed as MF
from . import milb_study as MS
from . import playlist as PL


def game_starters(pitches: list[dict]) -> dict:
    """{(game_pk, team_fielding_id): (date, pitcher_id, name)}: whoever threw the team's first pitch of the game."""
    first = {}
    for p in pitches:
        k = (p["game_pk"], p.get("team_fielding_id"))
        key = (p.get("inning") or 99, p.get("ab_number") or 0, p.get("pitch_number") or 0)
        if k not in first or key < first[k][0]:
            first[k] = (key, p["_date"], p.get("pitcher"), p.get("pitcher_name"))
    return {k: v[1:] for k, v in first.items()}


def pick_starter(starters: dict, pitcher_id: int | None, min_starts: int):
    c = Counter(v[1] for v in starters.values())
    if pitcher_id is None:
        pitcher_id, n = c.most_common(1)[0]
    else:
        n = c[pitcher_id]
    if n < min_starts:
        raise ValueError(f"pitcher {pitcher_id} has {n} cached starts (need {min_starts})")
    mine = sorted((v[0], k[0]) for k, v in starters.items() if v[1] == pitcher_id)
    name = next(v[2] for v in starters.values() if v[1] == pitcher_id)
    return pitcher_id, name, mine


def plan(pitches: list[dict], pitcher_id: int | None = None, n_starts: int = 4, min_starts: int = 8, limit: int = 8) -> dict:
    starters = game_starters(pitches)
    pid, name, mine = pick_starter(starters, pitcher_id, min_starts)
    target_date, target_pk = mine[-1]
    prev = sorted(mine[:-1], reverse=True)[:n_starts]               # most recent first, strictly before the planned game
    pool = []
    for age, (date, pk) in enumerate(prev):
        pool += [dict(p, _age=age, _date=date) for p in pitches if p["game_pk"] == pk and p.get("pitcher") == pid and p.get("type") == "pitch"]
    seen = {}
    for p in sorted((p for p in pitches if p["game_pk"] == target_pk and p.get("pitcher") == pid), key=lambda p: (p.get("inning") or 0, p.get("ab_number") or 0, p.get("pitch_number") or 0)):
        if p.get("batter") and p.get("stand") in ("L", "R"):
            seen.setdefault(p["batter"], dict(id=p["batter"], name=p.get("batter_name"), stand=p["stand"]))
    hist = MS.by_hitter([p for p in pitches if p["_date"] < target_date])
    plans = []
    for h in seen.values():
        hitter = dict(stand=h["stand"], name=h["name"], rows=hist.get(str(h["id"]), []))
        out = dict(id=h["id"], name=h["name"], stand=h["stand"], history_rows=len(hitter["rows"]), lists={})
        for nm in ("usage", "ride", "run"):
            pl = PL.playlist(nm, pool, hitter, 3, limit)
            e = dict(status="ok" if pl["pitches"] else "none", shapes=[list(s) for s in pl["shapes"]], n_pitches=len(pl["pitches"]))
            if pl.get("note"):
                e["trait"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in pl["note"].items()}
                if not pl["pitches"]:
                    e["why"] = e["trait"].get("why") or "slope interval includes zero"
            out["lists"][nm] = e
        plans.append(out)
    return dict(pitcher_id=pid, pitcher=name, planned_game=target_pk, planned_date=target_date, starts_pooled=[d for d, _ in prev], pool=len(pool), hitters=plans)


def to_markdown(label: str, r: dict) -> str:
    L = [f"# {label}: lineup plan vs {r['pitcher']} (game {r['planned_game']}, {r['planned_date']})", "",
         f"Pooled his {len(r['starts_pooled'])} previous starts ({', '.join(r['starts_pooled'])}), {r['pool']} pitches. Hitter history is this league's earlier games only.", "",
         "| Hitter | Side | Earlier tracked rows | Usage shapes | Ride | Run |", "|---|---|---|---|---|---|"]
    def shp(e):
        return "; ".join("-".join(s) for s in e["shapes"]) if e["shapes"] else "none"
    def tr(e):
        t = e.get("trait", {})
        return f"{t['slope']:+.2f} [{t['lo']:+.2f}, {t['hi']:+.2f}], {e['n_pitches']} pitches" if e["status"] == "ok" else f"no list: {e.get('why', 'not enough history')}"
    for p in r["hitters"]:
        ls = p["lists"]
        L.append(f"| {p['name']} | {p['stand']} | {p['history_rows']} | {shp(ls['usage'])} | {tr(ls['ride'])} | {tr(ls['run'])} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pitcher-id", type=int, default=None)
    ap.add_argument("--starts", type=int, default=4)
    ap.add_argument("--min-starts", type=int, default=8)
    a = ap.parse_args(argv)
    r = plan(MF.load(pathlib.Path(a.cache)), a.pitcher_id, a.starts, a.min_starts)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"milb_lineup_{a.label}.json").write_text(json.dumps(r, indent=1))
    (out / f"milb_lineup_{a.label}.md").write_text(to_markdown(a.label, r))
    print(to_markdown(a.label, r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
