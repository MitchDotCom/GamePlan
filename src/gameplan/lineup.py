"""One command, one starter, a whole lineup: every hitter's playlists in a single plan, optionally with a go/no-go page per hitter.

  python -m gameplan.lineup --pitcher-id 663903 --season 2025 --before 2025-06-11 --starts 4 --from-game 777433 --work <dir> [--pages]
  python -m gameplan.lineup ... --lineup lineup.json     # [{"id": 663457, "name": "Lars Nootbaar", "stand": "L"}, ...]

Writes <work>/plan.json and <work>/plan.md. A hitter whose history cannot be fetched is listed with the reason; the rest continue.
Pooled feeds, hitter seasons and downloaded clips are cached under <work>, so a rerun only does what is new.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from . import mlb_demo
from . import playlist as PL

NAMES = ("usage", "hitter_cost", "ride", "run")


def lineup_from_game(game_pk: int, pitcher_id: int) -> list[dict]:
    """The batters who faced this pitcher in one game, in the order they first appeared, with the side they hit from."""
    from . import videocut as V
    seen = {}
    for p in V.game_pitches(game_pk):
        if p.get("pitcher") == pitcher_id and p.get("batter") and p.get("stand") in ("L", "R"):
            seen.setdefault(p["batter"], dict(id=p["batter"], name=p.get("batter_name"), stand=p["stand"]))
    return list(seen.values())


def plan_hitter(rows: list[dict], h: dict, seasons: list[int], work: pathlib.Path, names=NAMES, n_shapes: int = 3, limit: int = 8, counts: bool = False) -> dict:
    out = dict(id=h["id"], name=h["name"], stand=h["stand"], lists={})
    hitter = dict(stand=h["stand"], name=h["name"])
    try:
        hitter["rows"] = PL.hitter_history(h["id"], seasons, work / "hitters")
    except Exception as e:
        out["error"] = f"history not fetched: {type(e).__name__}: {str(e)[:120]}"
        hitter["rows"] = []
    for nm in names:
        if nm != "usage" and not hitter["rows"]:
            out["lists"][nm] = dict(status="skipped", why="no history")
            continue
        pl = PL.playlist(nm, rows, hitter, n_shapes, limit)
        entry = dict(status="ok" if pl["pitches"] else "none", shapes=[list(s) for s in pl["shapes"]], pitches=[p["play_id"] for p in pl["pitches"]])
        if pl.get("note"):
            entry["trait"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in pl["note"].items()}
            if not pl["pitches"]:
                entry["why"] = entry["trait"].get("why") or "slope interval includes zero"
        entry["evidence"] = pl["evidence"]
        out["lists"][nm] = entry
        out.setdefault("_pl", {})[nm] = pl
    if counts:
        for b in PL.BUCKETS:
            pl = PL.playlist("usage", rows, hitter, n_shapes, limit, bucket=b)
            out.setdefault("counts", {})[b] = dict(status="ok" if pl["pitches"] else "none", shapes=[list(x) for x in pl["shapes"]], pitches=[p["play_id"] for p in pl["pitches"]],
                                                   pool=pl["pool"], **({"why": pl["why"]} if pl.get("why") else {}), evidence=pl["evidence"])
    return out


def to_markdown(starter: str, meta: dict, plans: list[dict]) -> str:
    L = [f"# Lineup plan vs {starter}", "",
         f"Pooled {meta['starts']} starts before {meta['before']}, {meta['pool']} pitches, recency half-life {PL.HALF_LIFE:g} starts. Hitter history {meta['seasons']}.", "",
         "| Hitter | Side | Usage shapes | Hitter-cost shapes | Ride | Run |", "|---|---|---|---|---|---|"]
    def shp(e):
        return "; ".join("-".join(s) for s in e["shapes"]) if e.get("shapes") else "none"
    def tr(e):
        if not e:
            return ""
        t = e.get("trait", {})
        if e["status"] == "ok":
            return f"{t['slope']:+.2f} [{t['lo']:+.2f}, {t['hi']:+.2f}], {len(e['pitches'])} clips"
        return f"no list: {e.get('why', '')}"
    for p in plans:
        ls = p["lists"]
        L.append(f"| {p['name']} | {p['stand']} | {shp(ls.get('usage', {}))} | {shp(ls.get('hitter_cost', {}))} | {tr(ls.get('ride'))} | {tr(ls.get('run'))} |"
                 + (f" {p['error']}" if p.get("error") else ""))
    if any(p.get("counts") for p in plans):
        L += ["", "## By count (descriptive, not validated)", "", "| Hitter | Side | " + " | ".join(PL.BUCKETS) + " |", "|---|---|" + "---|" * len(PL.BUCKETS)]
        for p in plans:
            c = p.get("counts", {})
            L.append(f"| {p['name']} | {p['stand']} | " + " | ".join((shp(c[b]) if c.get(b, {}).get("status") == "ok" else f"none ({c.get(b, {}).get('why', '')})") for b in PL.BUCKETS) + " |")
    L += ["", "Evidence: " + "; ".join(f"{k}: {v}" for k, v in PL.EVIDENCE.items()) + ". Ride and run are listed only when the slope's 95% interval excludes zero, and ride lists carry the thin tag."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitcher-id", type=int, required=True)
    ap.add_argument("--pitcher-name", default=None)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--before", required=True)
    ap.add_argument("--starts", type=int, default=5)
    ap.add_argument("--hitter-seasons", type=int, default=3)
    ap.add_argument("--lineup", default=None, help="JSON file of {id, name, stand}")
    ap.add_argument("--from-game", type=int, default=None, help="take the lineup from the batters who faced the pitcher in this game")
    ap.add_argument("--names", default=",".join(NAMES))
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--counts", action="store_true", help="add count-specific usage lists (first pitch, ahead, even, behind, two strikes); descriptive only")
    ap.add_argument("--pages", action="store_true", help="also build a go/no-go page per hitter and list (downloads clips)")
    ap.add_argument("--work", required=True)
    a = ap.parse_args(argv)
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    hitters = json.loads(pathlib.Path(a.lineup).read_text()) if a.lineup else lineup_from_game(a.from_game, a.pitcher_id)
    if not hitters:
        print("no hitters: give --lineup or --from-game")
        return 1
    starts = PL.recent_starts(a.pitcher_id, a.season, a.before, a.starts)
    rows = PL.pooled(a.pitcher_id, starts, work / "feeds")
    seasons = list(range(a.season - a.hitter_seasons + 1, a.season + 1))
    names = tuple(x for x in a.names.split(",") if x)
    plans = []
    for h in hitters:
        p = plan_hitter(rows, h, seasons, work, names, limit=a.limit, counts=a.counts)
        print(h["name"], {k: (v["status"], len(v.get("pitches", []))) for k, v in p["lists"].items()}, flush=True)
        if a.pages:
            for nm, pl in p.get("_pl", {}).items():
                if pl["pitches"]:
                    pg = work / "pages" / f"{h['id']}_{nm}.html"
                    pg.parent.mkdir(exist_ok=True)
                    mlb_demo.build_rows(pl["pitches"], work / "clips", pg, a.limit, title=f"Go / No-Go: {h['name']} ({h['stand']}), {nm}, last {pl['starts']} starts [{pl['evidence']}]")
                    p["lists"][nm]["page"] = str(pg)
        p.pop("_pl", None)
        plans.append(p)
    meta = dict(starts=len(starts), before=a.before, pool=len(rows), seasons=f"{seasons[0]} to {seasons[-1]}")
    (work / "plan.json").write_text(json.dumps(dict(pitcher_id=a.pitcher_id, **meta, hitters=plans), indent=1))
    (work / "plan.md").write_text(to_markdown(a.pitcher_name or str(a.pitcher_id), meta, plans))
    print(f"wrote {work / 'plan.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
