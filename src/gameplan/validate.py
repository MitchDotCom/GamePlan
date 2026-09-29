"""Out-of-sample viability check for the plan generator.

For each hitter: fit on the first TRAIN_FRAC of their swings (chronological), build a plan, then
score the held-out swings. Two questions:

1. Separation: do held-out swings in GO cells have higher whiff-adjusted contact quality (CQ) than
   swings in NO_GO cells?
2. Individualization: is that separation larger than for a league-only plan (no hitter data)?
   If not, the per-hitter part adds nothing and a team-wide plan would do as well.

The league prior for each hitter is built from OTHER hitters' training swings only.

    python -m gameplan.validate data/*_2025.csv
"""
from __future__ import annotations

import argparse
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from .evaluate import _select_rule
from .models import Hitter, Instruction, Pitch, Pitcher
from .plan import generate_grid_plan
from .savant import ContactQualityModel, SwingRow, contact_quality, parse_swings

TRAIN_FRAC = 0.6
MIN_TRAIN_SWINGS_PER_TYPE = 100
MIN_GROUP_SWINGS = 30


@dataclass
class HitterResult:
    batter: str
    n_train: int
    n_test: int
    go_n: int
    nogo_n: int
    gap: Optional[float]         # (CQ_GO - CQ_NOGO) / test baseline, hitter model
    league_gap: Optional[float]  # same, league-only model
    go_lift: Optional[float]     # CQ_GO / test baseline - 1
    nogo_lift: Optional[float]


def _split(rows: list[SwingRow]) -> tuple[list[SwingRow], list[SwingRow]]:
    rows = sorted(rows, key=lambda r: r.date)
    cut = int(len(rows) * TRAIN_FRAC)
    return rows[:cut], rows[cut:]


def _classify(plan, swings: list[SwingRow]) -> dict[Instruction, list[SwingRow]]:
    out: dict[Instruction, list[SwingRow]] = {i: [] for i in Instruction}
    for s in swings:
        p = Pitch("v", s.pitch_type, s.x, s.z, s.velo or 0.0)
        r = _select_rule(plan, p, 0)
        out[r.instruction if r else Instruction.CONDITIONAL].append(s)
    return out


def _gap(groups, base: float):
    go, ng = groups[Instruction.GO], groups[Instruction.NO_GO]
    if len(go) < MIN_GROUP_SWINGS or len(ng) < MIN_GROUP_SWINGS:
        return None, None, None
    cg, cn = contact_quality(go), contact_quality(ng)
    if cg is None or cn is None or base <= 0:
        return None, None, None
    return (cg - cn) / base, cg / base - 1, cn / base - 1


def validate(rows: list[SwingRow], **model_kw) -> list[HitterResult]:
    by_hitter: dict[str, list[SwingRow]] = {}
    for r in rows:
        by_hitter.setdefault(r.batter, []).append(r)
    splits = {b: _split(v) for b, v in by_hitter.items()}
    results = []
    for b, (train, test) in splits.items():
        league_train = [s for ob, (tr, _) in splits.items() if ob != b for s in tr]
        types = [t for t, n in Counter(s.pitch_type for s in train).items()
                 if n >= MIN_TRAIN_SWINGS_PER_TYPE]
        base_train = contact_quality(train)
        base_test = contact_quality(test)
        if not types or base_train is None or base_test is None:
            continue
        h = Hitter(b, baseline_cq=base_train)
        m_h = ContactQualityModel(train, league_train, **model_kw)
        m_l = ContactQualityModel([], league_train, **model_kw)
        g_h = _classify(generate_grid_plan(h, Pitcher("p"), m_h, types), test)
        g_l = _classify(generate_grid_plan(h, Pitcher("p"), m_l, types), test)
        gap, go_l, ng_l = _gap(g_h, base_test)
        lgap, _, _ = _gap(g_l, base_test)
        results.append(HitterResult(
            b, len(train), len(test),
            len(g_h[Instruction.GO]), len(g_h[Instruction.NO_GO]),
            gap, lgap, go_l, ng_l,
        ))
    return results


def deviation_reliability(rows: list[SwingRow], cell_ft: float = 8.0 / 12.0, min_n: int = 8):
    """Is a hitter's *deviation from league* stable? For cells with at least min_n swings in both the
    first and second half of a hitter's season, correlate (hitter CQ - league CQ) across halves.
    A location effect shared by everyone cancels out; what remains is individual. Near zero means the
    per-hitter part of the plan is noise at this sample size. Returns {batter: (r, n_cells)}."""
    import math
    from collections import defaultdict

    def key(s):
        return (s.pitch_type, math.floor(s.x / cell_ft), math.floor(s.z / cell_ft))

    by_h: dict[str, list[SwingRow]] = {}
    for r in rows:
        by_h.setdefault(r.batter, []).append(r)
    league: dict = defaultdict(lambda: defaultdict(list))
    for b, v in by_h.items():
        for s in v:
            league[key(s)][b].append(s)
    out = {}
    for b, v in by_h.items():
        a, c = _split(v)
        ga, gc = defaultdict(list), defaultdict(list)
        for s in a:
            ga[key(s)].append(s)
        for s in c:
            gc[key(s)].append(s)
        xs, ys = [], []
        for k in ga.keys() & gc.keys():
            if len(ga[k]) < min_n or len(gc[k]) < min_n:
                continue
            others = [s for ob, ss in league[k].items() if ob != b for s in ss]
            lq = contact_quality(others) if len(others) >= 30 else None
            qa, qc = contact_quality(ga[k]), contact_quality(gc[k])
            if None in (lq, qa, qc):
                continue
            xs.append(qa - lq)
            ys.append(qc - lq)
        if len(xs) >= 8:
            mx, my = statistics.mean(xs), statistics.mean(ys)
            sx = sum((x - mx) ** 2 for x in xs) ** 0.5
            sy = sum((y - my) ** 2 for y in ys) ** 0.5
            out[b] = ((sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)) if sx and sy else 0.0,
                      len(xs))
    return out


def summarize(results: list[HitterResult]) -> str:
    def f(v):
        return "  n/a" if v is None else f"{v:+.2f}"
    lines = ["batter    train  test  GO_n  NOGO_n  GO_lift NOGO_lift  gap  league_gap"]
    for r in results:
        lines.append(f"{r.batter:<9}{r.n_train:>6}{r.n_test:>6}{r.go_n:>6}{r.nogo_n:>8}"
                     f"{f(r.go_lift):>9}{f(r.nogo_lift):>10}{f(r.gap):>7}{f(r.league_gap):>11}")
    scored = [r for r in results if r.gap is not None]
    both = [r for r in scored if r.league_gap is not None]
    lines.append("")
    lines.append(f"hitters evaluated: {len(results)}, with enough GO and NO_GO swings: {len(scored)}")
    if scored:
        pos = sum(r.gap > 0 for r in scored)
        lines.append(f"GO beats NO_GO out of sample: {pos}/{len(scored)} hitters; "
                     f"mean gap {statistics.mean(r.gap for r in scored):+.3f} (fraction of baseline CQ)")
    if both:
        wins = sum(r.gap > r.league_gap for r in both)
        diffs = [r.gap - r.league_gap for r in both]
        lines.append(f"hitter model beats league-only plan: {wins}/{len(both)} hitters; "
                     f"mean gap improvement {statistics.mean(diffs):+.3f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--k-swing", type=float, default=30.0)
    ap.add_argument("--k-bip", type=float, default=15.0)
    a = ap.parse_args(argv)
    rows: list[SwingRow] = []
    for path in a.csv:
        with open(path, encoding="utf-8-sig") as fh:
            rows += parse_swings(fh.read())
    print(summarize(validate(rows, k_swing=a.k_swing, k_bip=a.k_bip)))
    rel = deviation_reliability(rows)
    print("\nsplit-half correlation of hitter-vs-league deviation (8in cells, n>=8 per half):")
    for b, (r, n) in sorted(rel.items()):
        print(f"  {b:<9} r={r:+.2f}  cells={n}")
    if rel:
        print(f"  median r={statistics.median(r for r, _ in rel.values()):+.2f} over {len(rel)} hitters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
