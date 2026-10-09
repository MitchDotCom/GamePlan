"""Per-player recognition profile from go/no-go trial logs (the CSV the page downloads).

Modeled on the structure of the Rangers/uHIT assessment described in the ABCA article (a fixed set of pitches, zone recognition and pitch-type recognition scored
separately, repeated over time, reviewed one-on-one). That article is a vendor-coauthored case report (ledger row 13, grade C); its baseline numbers (67% zone,
53% pitch type from 120 pitches) are context only. The measures here are standard signal-detection ones, so they can be compared across players and across tests of
different difficulty.

Two questions per pitch, in this order. (1) Strike or ball: the tracking row says whether the pitch crossed the zone (not the umpire's call).
  hit rate           "Strike" when it was a strike          false-alarm rate   "Strike" when it was a ball
  d'                 how well he separates the two (0 = guessing), independent of how strike-happy he is
  criterion c        positive = leans toward "Ball", negative = leans toward "Strike"
  accuracy           share correct; always read next to `majority_baseline`, the accuracy of always giving the better single answer on his trials
Rates use a log-linear correction (add 0.5 to each cell) so a perfect or empty cell does not give an infinite d'.
(2) Which pitch: he picks from that pitcher's own pitch types (the `options` column). With several choices there is no d'. Accuracy is read next to `chance_baseline` (the average of 1 over the number
of choices he was offered) and `majority_baseline` (always naming the most-thrown type). `by_pitch_type` is recall per thrown type; `confusions` lists what he named instead, most frequent first.

Breakdowns: the nine pockets, pitch family and type, distance from the zone edge, decision time, session by session. A cell is shown only with at least MIN_CELL trials and carries a Wilson
interval. `weak_cells` lists cells whose interval sits entirely below his own overall accuracy for that task. With many cells some will look weak by chance; it is a list of places to look at
on video with him, not a diagnosis.

  python -m gameplan.recognition_profile --trials gonogo_trials.csv --out <dir> [--player NAME]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import pathlib
from collections import defaultdict
from statistics import NormalDist, median

import numpy as np

MIN_CELL = 8
POCKETS = [f"{h}-{s}" for h in ("high", "mid", "low") for s in ("in", "mid", "away")]
ND = NormalDist()


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (float(c - h), float(c + h))


def sdt(hit: int, n_sig: int, fa: int, n_noise: int) -> dict:
    """Signal-detection summary with a log-linear correction. Needs trials of both kinds, else d' is None."""
    if n_sig == 0 or n_noise == 0:
        return dict(hit_rate=None, fa_rate=None, d_prime=None, criterion=None)
    h = (hit + 0.5) / (n_sig + 1)
    f = (fa + 0.5) / (n_noise + 1)
    return dict(hit_rate=round(hit / n_sig, 3), fa_rate=round(fa / n_noise, 3), d_prime=round(ND.inv_cdf(h) - ND.inv_cdf(f), 3), criterion=round(-0.5 * (ND.inv_cdf(h) + ND.inv_cdf(f)), 3))


def load(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            r["correct"] = None if r.get("correct") in ("", None) else int(float(r["correct"]))
            r["rt_ms"] = float(r["rt_ms"]) if r.get("rt_ms") not in ("", None) else None
            for k in ("px", "pz", "sz_top", "sz_bot"):
                r[k] = float(r[k]) if r.get(k) not in ("", None) else None
            rows.append(r)
    return rows


def edge_bucket(r: dict):
    """Distance of the pitch from the zone edge, feet: negative inside. Buckets of 3 inches around the edge."""
    if None in (r.get("px"), r.get("pz"), r.get("sz_top"), r.get("sz_bot")):
        return None
    d = max(abs(r["px"]) - 0.83, r["pz"] - r["sz_top"], r["sz_bot"] - r["pz"])
    return "inside, deeper than 3 in" if d < -0.25 else "inside, within 3 in of the edge" if d < 0 else "outside, within 3 in of the edge" if d < 0.25 else "outside, more than 3 in"


def n_options(r: dict):
    o = [x for x in (r.get("options") or "").split("|") if x]
    return len(o) or None


def task_summary(rows: list[dict], task: str = "zone") -> dict:
    sc = [r for r in rows if r["correct"] is not None]
    if not sc:
        return dict(n=0)
    k = sum(r["correct"] for r in sc)
    lo, hi = wilson(k, len(sc))
    if task == "zone":
        sig = [r for r in sc if r["key"] == "Strike"]
        noi = [r for r in sc if r["key"] == "Ball"]
        extra = dict(majority_baseline=round(max(len(sig), len(noi)) / len(sc), 3), **sdt(sum(r["call"] == "Strike" for r in sig), len(sig), sum(r["call"] == "Strike" for r in noi), len(noi)))
    else:
        from collections import Counter
        no = [n_options(r) for r in sc]
        extra = dict(majority_baseline=round(max(Counter(r["key"] for r in sc).values()) / len(sc), 3),
                     chance_baseline=round(sum(1 / n for n in no if n) / len([n for n in no if n]), 3) if any(no) else None)
    rt = [r["rt_ms"] for r in sc if r["rt_ms"] is not None]
    return dict(n=len(sc), accuracy=round(k / len(sc), 3), ci=[round(lo, 3), round(hi, 3)], **extra,
                median_rt_ms=int(median(rt)) if rt else None,
                median_rt_correct_ms=int(median([r["rt_ms"] for r in sc if r["correct"] and r["rt_ms"] is not None] or [0])) or None,
                median_rt_wrong_ms=int(median([r["rt_ms"] for r in sc if not r["correct"] and r["rt_ms"] is not None] or [0])) or None)


def cells(rows: list[dict], keyfn, min_cell: int = MIN_CELL, task: str = "zone") -> dict:
    g = defaultdict(list)
    for r in rows:
        if r["correct"] is not None:
            k = keyfn(r)
            if k:
                g[k].append(r)
    out = {}
    for k, rs in sorted(g.items()):
        n, c = len(rs), sum(r["correct"] for r in rs)
        if n >= min_cell:
            lo, hi = wilson(c, n)
            out[k] = dict(n=n, accuracy=round(c / n, 3), ci=[round(lo, 3), round(hi, 3)])
            if task == "zone":
                out[k]["strike_rate"] = round(sum(r["call"] == "Strike" for r in rs) / n, 3)
        else:
            out[k] = dict(n=n, accuracy=None, note=f"fewer than {min_cell} trials")
    return out


def weak_cells(by_cell: dict, overall: float) -> list:
    return sorted([(k, v["accuracy"], v["n"]) for k, v in by_cell.items() if v.get("accuracy") is not None and v["ci"][1] < overall], key=lambda t: t[1])


def confusions(rows: list[dict]) -> list:
    """What he named when he was wrong, by thrown type: [(thrown, named, count)] most frequent first."""
    from collections import Counter
    c = Counter((r["key"], r["call"]) for r in rows if r["correct"] == 0)
    return [(a, b, n) for (a, b), n in c.most_common()]


def sessions(rows: list[dict], task: str = "zone") -> list:
    g = defaultdict(list)
    for r in rows:
        g[(r["session"], r["mode"])].append(r)
    out = []
    for (s, m), rs in sorted(g.items()):
        t = task_summary(rs, task)
        if t["n"]:
            out.append(dict(session=s, mode=m, n=t["n"], accuracy=t["accuracy"], d_prime=t.get("d_prime"), median_rt_ms=t["median_rt_ms"]))
    return out


def profile(rows: list[dict], player: str) -> dict:
    mine = [r for r in rows if r["player"] == player]
    out = dict(player=player, trials=len(mine), unscored=sum(r["correct"] is None for r in mine), sessions=len({r["session"] for r in mine}))
    for task in ("zone", "pitch"):
        tr = [r for r in mine if r["task"] == task]
        t = task_summary(tr, task)
        ent = dict(summary=t)
        if t["n"]:
            ent["by_pocket"] = cells(tr, lambda r: r["pocket"] or None, task=task)
            ent["by_family"] = cells(tr, lambda r: r["family"] or None, task=task)
            ent["by_pitch_type"] = cells(tr, lambda r: r["pitch_type"] or None, task=task)
            ent["by_edge_distance"] = cells(tr, edge_bucket, task=task)
            ent["by_session"] = sessions(tr, task)
            if task == "pitch":
                ent["confusions"] = confusions(tr)
            ent["weak_cells"] = {name: weak_cells(ent[name], t["accuracy"]) for name in ("by_pocket", "by_family", "by_pitch_type", "by_edge_distance")}
        out[task] = ent
    return out


def compare(rows: list[dict], player: str, task: str, session_a: str, session_b: str, reps: int = 2000, seed: int = 3) -> dict:
    """Change from session A to session B, bootstrapped over trials: d' for the zone task, accuracy for the pitch task (no d' with several choices). Needs 30 scored trials in each."""
    A = [r for r in rows if r["player"] == player and r["task"] == task and r["session"] == session_a and r["correct"] is not None]
    B = [r for r in rows if r["player"] == player and r["task"] == task and r["session"] == session_b and r["correct"] is not None]
    if min(len(A), len(B)) < 30:
        return dict(ok=False, why=f"need 30 scored trials in each session (have {len(A)} and {len(B)})")
    def dp(rs):
        if task != "zone":
            return sum(r["correct"] for r in rs) / len(rs)
        sig = [r for r in rs if r["key"] == "Strike"]
        noi = [r for r in rs if r["key"] == "Ball"]
        return sdt(sum(r["call"] == "Strike" for r in sig), len(sig), sum(r["call"] == "Strike" for r in noi), len(noi))["d_prime"]
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(reps):
        a = [A[i] for i in rng.integers(0, len(A), len(A))]
        b = [B[i] for i in rng.integers(0, len(B), len(B))]
        da, db = dp(a), dp(b)
        if da is not None and db is not None:
            diffs.append(db - da)
    est = dp(B) - dp(A)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return dict(ok=True, measure="d_prime" if task == "zone" else "accuracy", change_d_prime=round(est, 3), ci=[round(float(lo), 3), round(float(hi), 3)], n_a=len(A), n_b=len(B))


def _grid(by_pocket: dict) -> str:
    cell = lambda k: by_pocket.get(k, {})
    def td(k):
        c = cell(k)
        if c.get("accuracy") is None:
            return f"<td class='na'>{k}<br>n={c.get('n', 0)}<br>too few</td>"
        a = c["accuracy"]
        shade = int(255 - 160 * max(0, min(1, (a - 0.4) / 0.6)))
        return f"<td style='background:rgb({shade},{200 if a > .6 else 120},{shade})'>{k}<br><b>{a:.0%}</b><br>n={c['n']}<br><small>{c['ci'][0]:.0%} to {c['ci'][1]:.0%}</small></td>"
    rows = "".join("<tr>" + "".join(td(f"{h}-{s}") for s in ("in", "mid", "away")) + "</tr>" for h in ("high", "mid", "low"))
    return f"<table class='g'>{rows}</table>"


def render_html(pr: dict) -> str:
    h = [f"<!doctype html><meta charset=utf-8><title>Recognition profile, {html.escape(pr['player'])}</title><style>body{{font:14px/1.4 system-ui;max-width:900px;margin:20px auto;padding:0 12px}}"
         "table{border-collapse:collapse;margin:6px 0}td,th{border:1px solid #bbb;padding:5px 8px;text-align:left}.g td{text-align:center;width:120px;height:80px}.na{color:#888}</style>",
         f"<h1>{html.escape(pr['player'])}</h1><p>{pr['trials']} trials, {pr['sessions']} sessions, {pr['unscored']} not scored (no answer key). Pockets are as the batter sees them (in = toward his body).</p>"]
    for task, label in (("zone", "Strike or ball"), ("pitch", "Which pitch (his pitcher's own pitch types)")):
        t = pr[task]["summary"]
        h.append(f"<h2>{label}</h2>")
        if not t["n"]:
            h.append("<p>No scored trials.</p>")
            continue
        if task == "zone":
            sdt_txt = f"d' <b>{t['d_prime']}</b>, criterion {t['criterion']} (positive = leans Ball). Hit rate {t['hit_rate']}, false-alarm rate {t['fa_rate']}. "
            base = f"always answering the better single answer would score {t['majority_baseline']:.0%}. "
        else:
            sdt_txt = ""
            base = (f"guessing among the choices he was offered would score about {t['chance_baseline']:.0%}, and always naming the most-thrown type {t['majority_baseline']:.0%}. "
                    if t.get("chance_baseline") else f"always naming the most-thrown type would score {t['majority_baseline']:.0%}. ")
        h.append(f"<p>{t['n']} scored. Accuracy <b>{t['accuracy']:.0%}</b> (95% {t['ci'][0]:.0%} to {t['ci'][1]:.0%}); {base}{sdt_txt}"
                 f"Median decision {t['median_rt_ms']} ms (correct {t['median_rt_correct_ms']}, wrong {t['median_rt_wrong_ms']}).</p>")
        h.append("<h3>By pocket</h3>" + _grid(pr[task]["by_pocket"]))
        for name, title in (("by_family", "By pitch family"), ("by_pitch_type", "By pitch type"), ("by_edge_distance", "By distance from the zone edge")):
            d = pr[task][name]
            if d:
                h.append(f"<h3>{title}</h3><table><tr><th></th><th>n</th><th>accuracy</th><th>95% interval</th><th>{'said strike' if task == 'zone' else ''}</th></tr>" + "".join(
                    f"<tr><td>{html.escape(k)}</td><td>{v['n']}</td><td>{'' if v.get('accuracy') is None else format(v['accuracy'], '.0%')}</td><td>{'' if v.get('accuracy') is None else format(v['ci'][0], '.0%') + ' to ' + format(v['ci'][1], '.0%')}</td>"
                    f"<td>{'' if v.get('accuracy') is None or 'strike_rate' not in v else format(v['strike_rate'], '.0%')}</td></tr>" for k, v in d.items()) + "</table>")
        wk = [(n, c) for n, cs in pr[task]["weak_cells"].items() for c in cs]
        if wk:
            h.append("<h3>Places to look at on video</h3><p>Cells whose whole interval sits below his own average. With this many cells, some will show up by chance; treat as a list to review, not a diagnosis.</p><ul>" +
                     "".join(f"<li>{html.escape(n.replace('by_', ''))}: {html.escape(c[0])}, {c[1]:.0%} on {c[2]} trials</li>" for n, c in wk) + "</ul>")
        if pr[task].get("confusions"):
            h.append("<h3>What he named instead</h3><table><tr><th>thrown</th><th>he said</th><th>times</th></tr>" + "".join(
                f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{n}</td></tr>" for a, b, n in pr[task]["confusions"][:12]) + "</table>")
        if pr[task]["by_session"]:
            h.append("<h3>Session by session</h3><table><tr><th>session</th><th>mode</th><th>n</th><th>accuracy</th><th>d'</th><th>median ms</th></tr>" + "".join(
                f"<tr><td>{s['session']}</td><td>{s['mode']}</td><td>{s['n']}</td><td>{s['accuracy']:.0%}</td><td>{s['d_prime']}</td><td>{s['median_rt_ms']}</td></tr>" for s in pr[task]["by_session"]) + "</table>")
    return "\n".join(h)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--player", default=None)
    a = ap.parse_args(argv)
    rows = load(a.trials)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    players = [a.player] if a.player else sorted({r["player"] for r in rows})
    summary = [["player", "trials", "zone_n", "zone_accuracy", "zone_d_prime", "pitch_n", "pitch_accuracy", "pitch_chance_baseline"]]
    for p in players:
        pr = profile(rows, p)
        safe = "".join(c if c.isalnum() else "_" for c in p)
        (out / f"profile_{safe}.json").write_text(json.dumps(pr, indent=1))
        (out / f"profile_{safe}.html").write_text(render_html(pr))
        z, t = pr["zone"]["summary"], pr["pitch"]["summary"]
        summary.append([p, pr["trials"], z.get("n"), z.get("accuracy"), z.get("d_prime"), t.get("n"), t.get("accuracy"), t.get("chance_baseline")])
    with open(out / "team_summary.csv", "w", newline="") as f:
        csv.writer(f).writerows(summary)
    print(f"{len(players)} players written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
