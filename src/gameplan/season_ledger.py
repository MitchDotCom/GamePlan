"""Season ledger and leaderboard: how well each hitter recognizes location (strike or ball) and pitch type, over the year, comparable across hitters.

  python -m gameplan.season_ledger --trials t1.csv trials.jsonl --out <dir> [--mode assess] [--min-n 30]

Reads the answer log (the CSV the page downloads, or the server's trials.jsonl; assessment rows are scored from the private keys by app_server before they are exported).
Rules that keep a leaderboard honest:
  * Only ASSESSMENT answers are ranked by default. Training packs are chosen per starter, differ in difficulty and show feedback, so a training score says what was in the pack more than what the hitter can do.
    `--mode train` ranks training answers anyway and labels the board.
  * Boards are never mixed across camera types (broadcast video, hitter's-eye drawing, behind-home drawing): each camera class is its own board.
  * A hitter with fewer than `--min-n` scored answers on a metric is listed but not ranked, and every number carries n and a 95% Wilson interval.
  * `tier` compares a hitter's interval with the group's pooled accuracy: above, below, or not distinguishable. Most hitters will be not distinguishable at these sample sizes, and the board says so.
  * `vs_peers` is accuracy minus what the OTHER hitters scored on the same pitch (needs 4 others on that pitch), so a hitter who happened to get the easy pitches is not credited for it.
Per hitter: strike/ball (accuracy, d', criterion), edge pitches within 3 in of the zone (the hard part of strike or ball), pitch type (accuracy against the chance level for the choices offered, recall by thrown type),
decision time, the nine location pockets, and a monthly trend. Nothing here is validated against game performance; it describes recognition on this test.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import pathlib
from collections import defaultdict
from statistics import median

from . import recognition_profile as RP

MIN_N = 30
PEER_MIN_OTHERS = 4
EDGE_FT = 0.25


def camera_class(c: str) -> str:
    c = c or "broadcast"
    return "drawn: " + c.split(":", 1)[1].replace("_", " ") if c.startswith("sim") and ":" in c else "drawn" if c.startswith("sim") else c


def load_any(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        if str(p).endswith(".jsonl"):
            raw = [json.loads(l) for l in pathlib.Path(p).read_text().splitlines() if l.strip()]
        else:
            raw = list(csv.DictReader(open(p, encoding="utf-8-sig")))
        rows += raw
    out, seen = [], set()
    for r in rows:
        if r.get("id") in seen:
            continue
        seen.add(r.get("id"))
        r = dict(r)
        r["correct"] = None if r.get("correct") in ("", None) else int(float(r["correct"]))
        r["rt_ms"] = float(r["rt_ms"]) if r.get("rt_ms") not in ("", None) else None
        for k in ("px", "pz", "sz_top", "sz_bot"):
            r[k] = float(r[k]) if r.get(k) not in ("", None) else None
        r["camera_class"] = camera_class(r.get("camera"))
        r["month"] = (r.get("ts") or "")[:7]
        out.append(r)
    return out


def is_edge(r: dict) -> bool:
    if None in (r.get("px"), r.get("pz"), r.get("sz_top"), r.get("sz_bot")):
        return False
    return abs(max(abs(r["px"]) - 0.83, r["pz"] - r["sz_top"], r["sz_bot"] - r["pz"])) < EDGE_FT


def peer_expectation(rows: list[dict]) -> dict:
    """{(player, trial id): mean score of the OTHER hitters on the same pitch and question}, only where at least PEER_MIN_OTHERS others answered it."""
    by = defaultdict(list)
    for r in rows:
        if r["correct"] is not None:
            by[(r["pack"], r["clip"], r["task"])].append(r)
    exp = {}
    for rs in by.values():
        tot, n = sum(x["correct"] for x in rs), len(rs)
        for r in rs:
            if n - 1 >= PEER_MIN_OTHERS:
                exp[r["id"]] = (tot - r["correct"]) / (n - 1)
    return exp


def metric(rs: list[dict], exp: dict) -> dict:
    sc = [r for r in rs if r["correct"] is not None]
    if not sc:
        return dict(n=0)
    k = sum(r["correct"] for r in sc)
    lo, hi = RP.wilson(k, len(sc))
    pe = [r["correct"] - exp[r["id"]] for r in sc if r["id"] in exp]
    return dict(n=len(sc), accuracy=round(k / len(sc), 3), ci=[round(lo, 3), round(hi, 3)], vs_peers=round(sum(pe) / len(pe), 3) if len(pe) >= 10 else None, n_vs_peers=len(pe))


def player_ledger(rs: list[dict], exp: dict) -> dict:
    z = [r for r in rs if r["task"] == "zone"]
    pt = [r for r in rs if r["task"] == "pitch"]
    out = dict(trials=len(rs), sessions=len({r["session"] for r in rs}), first=min((r["ts"] for r in rs), default=None), last=max((r["ts"] for r in rs), default=None))
    out["strike_ball"] = dict(metric(z, exp), **{k: v for k, v in RP.task_summary(z, "zone").items() if k in ("d_prime", "criterion", "majority_baseline", "median_rt_ms")})
    out["edge"] = metric([r for r in z if is_edge(r)], exp)
    out["pitch_type"] = dict(metric(pt, exp), **{k: v for k, v in RP.task_summary(pt, "pitch").items() if k in ("chance_baseline", "majority_baseline", "median_rt_ms")})
    ct = out["pitch_type"].get("chance_baseline")
    out["pitch_type"]["lift_over_chance"] = None if ct is None or not out["pitch_type"].get("n") else round(out["pitch_type"]["accuracy"] - ct, 3)
    out["by_pocket"] = RP.cells(z, lambda r: r.get("pocket") or None, task="zone")
    out["recall_by_type"] = RP.cells(pt, lambda r: r.get("pitch_type") or None, task="pitch")
    out["confusions"] = RP.confusions(pt)[:8]
    months = defaultdict(lambda: defaultdict(list))
    for r in rs:
        if r["correct"] is not None and r["month"]:
            months[r["month"]][r["task"]].append(r["correct"])
    out["trend"] = [dict(month=m, **{t: dict(n=len(v), accuracy=round(sum(v) / len(v), 3)) for t, v in sorted(d.items())}) for m, d in sorted(months.items())]
    return out


def tier(m: dict, pooled: float | None, min_n: int) -> str:
    if not m.get("n") or m["n"] < min_n or pooled is None:
        return "not ranked (too few answers)"
    return "above group" if m["ci"][0] > pooled else "below group" if m["ci"][1] < pooled else "not distinguishable from group"


def boards(rows: list[dict], mode: str = "assess", min_n: int = MIN_N) -> dict:
    """{camera class: {players: {...}, leaderboards: {metric: [...]}, pooled: {...}}} for the chosen mode."""
    rows = [r for r in rows if r.get("mode") == mode and r.get("player")]
    out = {}
    for cc in sorted({r["camera_class"] for r in rows}):
        rs = [r for r in rows if r["camera_class"] == cc]
        exp = peer_expectation(rs)
        players = {p: player_ledger([r for r in rs if r["player"] == p], exp) for p in sorted({r["player"] for r in rs})}
        pooled = {}
        for name, sel in (("strike_ball", lambda r: r["task"] == "zone"), ("edge", lambda r: r["task"] == "zone" and is_edge(r)), ("pitch_type", lambda r: r["task"] == "pitch")):
            s = [r for r in rs if sel(r) and r["correct"] is not None]
            pooled[name] = round(sum(r["correct"] for r in s) / len(s), 3) if s else None
        lb = {}
        for name in ("strike_ball", "edge", "pitch_type"):
            ent = []
            for p, led in players.items():
                m = led[name]
                ent.append(dict(player=p, n=m.get("n", 0), accuracy=m.get("accuracy"), ci=m.get("ci"), vs_peers=m.get("vs_peers"), tier=tier(m, pooled[name], min_n),
                                ranked=bool(m.get("n", 0) >= min_n)))
            ent.sort(key=lambda e: (not e["ranked"], -(e["accuracy"] or 0), -e["n"]))
            rank = 0
            for e in ent:
                rank += e["ranked"]
                e["rank"] = rank if e["ranked"] else None
            lb[name] = ent
        out[cc] = dict(players=players, pooled=pooled, leaderboards=lb, n_players=len(players), min_n=min_n, mode=mode)
    return out


LABELS = dict(strike_ball="Strike or ball", edge="Edge pitches (within 3 in of the zone edge)", pitch_type="Which pitch")


def render_html(b: dict) -> str:
    h = ["<!doctype html><meta charset=utf-8><title>Recognition leaderboard</title><style>body{font:14px/1.4 system-ui;max-width:980px;margin:20px auto;padding:0 12px}table{border-collapse:collapse;margin:6px 0 18px}"
         "td,th{border:1px solid #bbb;padding:5px 8px;text-align:left}.n{text-align:right}.mut{color:#777}.up{color:#0a6b3d;font-weight:600}.dn{color:#a3361c;font-weight:600}</style>"]
    if not b:
        return h[0] + "<p>No answers for this mode yet.</p>"
    for cc, d in b.items():
        h.append(f"<h1>{html.escape(cc)}</h1><p>{d['n_players']} hitters, {html.escape(d['mode'])} answers only. Ranked from {d['min_n']} scored answers; the interval is 95%. "
                 "Most hitters are not distinguishable from the group at these sample sizes. vs peers = accuracy minus what the other hitters scored on the same pitches. This describes recognition on this test, not game performance.</p>")
        for name, ent in d["leaderboards"].items():
            h.append(f"<h2>{LABELS[name]}</h2><p class=mut>Group accuracy {('-' if d['pooled'][name] is None else format(d['pooled'][name], '.0%'))}</p>"
                     "<table><tr><th>#</th><th>Hitter</th><th class=n>n</th><th class=n>Accuracy</th><th>95% interval</th><th class=n>vs peers</th><th>Reading</th></tr>")
            for e in ent:
                cls = "up" if e["tier"].startswith("above") else "dn" if e["tier"].startswith("below") else "mut"
                acc = "" if e["accuracy"] is None else format(e["accuracy"], ".0%")
                ci = "" if not e["ci"] else f"{e['ci'][0]:.0%} to {e['ci'][1]:.0%}"
                vp = "" if e["vs_peers"] is None else f"{e['vs_peers'] * 100:+.0f} pts"
                h.append(f"<tr><td>{e['rank'] or ''}</td><td>{html.escape(e['player'])}</td><td class=n>{e['n']}</td><td class=n>{acc}</td><td>{ci}</td><td class=n>{vp}</td><td class={cls}>{html.escape(e['tier'])}</td></tr>")
            h.append("</table>")
    return "\n".join(h)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="assess", choices=["assess", "train"])
    ap.add_argument("--min-n", type=int, default=MIN_N)
    a = ap.parse_args(argv)
    b = boards(load_any(a.trials), a.mode, a.min_n)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leaderboard.json").write_text(json.dumps(b, indent=1))
    (out / "leaderboard.html").write_text(render_html(b))
    with open(out / "leaderboard.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["camera", "metric", "rank", "hitter", "n", "accuracy", "ci_low", "ci_high", "vs_peers", "reading"])
        for cc, d in b.items():
            for name, ent in d["leaderboards"].items():
                for e in ent:
                    w.writerow([cc, name, e["rank"] or "", e["player"], e["n"], e["accuracy"] if e["accuracy"] is not None else "", *(e["ci"] or ["", ""]), e["vs_peers"] if e["vs_peers"] is not None else "", e["tier"]])
    print(f"{sum(d['n_players'] for d in b.values())} hitters across {len(b)} camera class(es), written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
