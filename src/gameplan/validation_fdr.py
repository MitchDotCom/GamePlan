"""Validation plan V4: Benjamini-Hochberg over the pre-registered grid, from the existing result files (no model reruns).

p-values are a normal approximation to the percentile bootstrap: se = (hi - lo) / 3.92, one-sided p = 1 - Phi(estimate / se).
Families, in every season: V1 (cost lift per shape and path), V2 (model path minus best baseline), Gate 0 B2 (P minus L).
"""
from __future__ import annotations

import argparse
import math
import pathlib
import re
from collections import defaultdict

SEASONS = (2025, 2024, 2023, 2022)
Q = 0.05
NUM = r"([+-]?\d+\.\d+)"
V1 = re.compile(rf"^(S\d) (\w+): cost lift {NUM} \[{NUM}, {NUM}\]")
V2 = re.compile(rf"^(S\d) (\w) vs best baseline \w+: {NUM} \[{NUM}, {NUM}\]")
B2 = re.compile(rf"^(S\d): P {NUM} - L {NUM} = {NUM} \[{NUM}, {NUM}\]")

_OUT: list[str] = []


def say(msg: str = "") -> None:
    print(msg, flush=True)
    _OUT.append(msg)


def phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def p_one_sided(est: float, lo: float, hi: float) -> float:
    se = (hi - lo) / 3.92
    if se <= 0:
        return 0.0 if est > 0 else 1.0
    return 1.0 - phi(est / se)


def collect(docs: pathlib.Path):
    tests = []   # (season, family, shape, path, estimate, p, uncorrected pass)
    for y in SEASONS:
        f = docs / f"validation_results_V1V3_{y}.txt"
        for line in f.read_text().splitlines():
            m = V1.match(line)
            if m:
                s, p, est, lo, hi = m.group(1), m.group(2), *map(float, m.groups()[2:])
                tests.append((y, "V1", s, p, est, p_one_sided(est, lo, hi), lo > 0))
                continue
            m = V2.match(line)
            if m:
                s, p, est, lo, hi = m.group(1), m.group(2), *map(float, m.groups()[2:])
                tests.append((y, "V2", s, p, est, p_one_sided(est, lo, hi), lo > 0))
        f = docs / f"gate0_results_{y}_primary.txt"
        for line in f.read_text().splitlines():
            m = B2.match(line)
            if m:
                s = m.group(1)
                est, lo, hi = float(m.group(4)), float(m.group(5)), float(m.group(6))
                tests.append((y, "B2", s, "P-L", est, p_one_sided(est, lo, hi), lo > 0))
    return tests


def bh(ps, q=Q):
    """Boolean list: which hypotheses are rejected at false-discovery rate q."""
    n = len(ps)
    order = sorted(range(n), key=lambda i: ps[i])
    cut = -1
    for rank, i in enumerate(order, 1):
        if ps[i] <= q * rank / n:
            cut = rank
    keep = [False] * n
    for rank, i in enumerate(order, 1):
        if rank <= cut:
            keep[i] = True
    return keep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    tests = collect(pathlib.Path(a.docs))
    keep = bh([t[5] for t in tests])
    say(f"V4: Benjamini-Hochberg at q = {Q} over {len(tests)} tests (V1, V2 and B2, four seasons jointly). p-values are a normal approximation to the bootstrap intervals.")
    for fam in ("V1", "V2", "B2"):
        idx = [i for i, t in enumerate(tests) if t[1] == fam]
        raw = sum(tests[i][6] for i in idx)
        cor = sum(keep[i] for i in idx)
        say(f"{fam}: {len(idx)} tests, {raw} pass uncorrected (interval above 0), {cor} survive correction")
    allraw = sum(t[6] for t in tests)
    allcor = sum(keep)
    say(f"All: {allraw} pass uncorrected, {allcor} survive ({allcor / max(allraw, 1):.0%} of the uncorrected passes)")
    say("\nPer conclusion: seasons passing uncorrected / seasons surviving correction, and grade (A 4 survive, B 3, C passes uncorrected in 3 or more but survives in fewer, F otherwise)")
    groups = defaultdict(list)
    for i, t in enumerate(tests):
        groups[(t[1], t[2], t[3])].append(i)
    for (fam, shape, path), idx in sorted(groups.items()):
        unc = sum(tests[i][6] for i in idx)
        sur = sum(keep[i] for i in idx)
        grade = "A" if sur == 4 else "B" if sur == 3 else "C" if unc >= 3 else "F"
        if fam == "V2" and unc == 0:
            say(f"{fam} {shape} {path}: {unc}/4 uncorrected, {sur}/4 survive  {grade}")
        elif unc or sur:
            say(f"{fam} {shape} {path}: {unc}/4 uncorrected, {sur}/4 survive  {grade}")
    say("\nPer season, tests surviving correction")
    for y in SEASONS:
        say(f"{y}: " + ", ".join(f"{fam} {sum(keep[i] for i, t in enumerate(tests) if t[0] == y and t[1] == fam)}/{sum(1 for t in tests if t[0] == y and t[1] == fam)}" for fam in ("V1", "V2", "B2")))
    if a.out:
        pathlib.Path(a.out).write_text("\n".join(_OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
