"""Structured coach reports and a per-coach accuracy ledger.

Report format (CSV, one row per tag; several rows share a report_id):

    report_id,coach_id,hitter_id,date,family,vert,horiz,whiff_delta,contact_delta,confidence,notes
    r1,coachA,665742,2025-05-01,FB,HIGH,,+0.10,-0.03,2,"catches up late on elevated velo"

family: FB | BRK | OFF (blank = all).   vert: LOW | MID | HIGH (blank = all).   horiz: IN | MID | AWAY.
whiff_delta: + means he misses more than a typical hitter, in probability points per swing.
contact_delta: + means more damage on contact, in xwOBA points.   confidence: 1 low, 2 medium, 3 high.

Accuracy: after a report date, the hitter's tracked swings show his real deviation from league in each
(pitch family, height) cell. The ledger compares each coach's tags with those deviations, fits how much
of a coach's stated deviation shows up in the data (slope through the origin), shrinks that toward a
prior when the coach has few scored cells, and returns a trust weight in [0, 1] separately for whiff
and contact. merge_reports scales tags by that trust before they enter the model, so a coach whose
reports have not matched the data moves the plan less."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .coach import FAMILY_OF, CoachProfile, CoachTag, vert_region
from .savant import SwingRow

FAMILIES = ("FB", "BRK", "OFF")
VERTS = ("LOW", "MID", "HIGH")
PRIOR_TRUST = 0.3        # before any evidence: a new coach counts for 30%
PRIOR_STRENGTH = 20.0    # scored cells worth of belief in the prior


@dataclass(frozen=True)
class CoachReport:
    report_id: str
    coach_id: str
    hitter_id: str
    date: str
    tags: tuple[CoachTag, ...]
    notes: str = ""


def _opt(v: str) -> Optional[str]:
    v = (v or "").strip().upper()
    return v or None


def load_reports_csv(text: str) -> list[CoachReport]:
    rows: dict[str, list[dict]] = defaultdict(list)
    for r in csv.DictReader(io.StringIO(text)):
        rows[r["report_id"]].append(r)
    out = []
    for rid, rs in rows.items():
        head = rs[0]
        tags = []
        for r in rs:
            fam, vert, horiz = _opt(r.get("family")), _opt(r.get("vert")), _opt(r.get("horiz"))
            if fam and fam not in FAMILIES or vert and vert not in VERTS or horiz and horiz not in ("IN", "MID", "AWAY"):
                raise ValueError(f"report {rid}: bad family/vert/horiz ({fam}, {vert}, {horiz})")
            conf = int(float(r.get("confidence") or 2))
            if conf not in (1, 2, 3):
                raise ValueError(f"report {rid}: confidence must be 1, 2 or 3")
            tags.append(CoachTag(fam, vert, horiz, float(r.get("whiff_delta") or 0.0),
                                 float(r.get("contact_delta") or 0.0), conf))
        out.append(CoachReport(rid, head["coach_id"], head["hitter_id"], head["date"], tuple(tags),
                               head.get("notes", "")))
    return out


TEMPLATE_CSV = ("report_id,coach_id,hitter_id,date,family,vert,horiz,whiff_delta,contact_delta,confidence,notes\n"
                'r1,coachA,000000,2026-04-15,FB,HIGH,,0.10,-0.03,2,"example row"\n')


def cell_signal(report: CoachReport) -> dict[tuple[str, str], tuple[float, float]]:
    """Net stated (whiff, contact) deviation per (family, height) cell, spreading blank dimensions."""
    out = {}
    for fam in FAMILIES:
        for vert in VERTS:
            w = c = 0.0
            hit = False
            for t in report.tags:
                if (t.family in (None, fam)) and (t.vert in (None, vert)):
                    w += t.whiff_delta
                    c += t.contact_delta
                    hit = True
            if hit:
                out[(fam, vert)] = (w, c)
    return out


def tracked_deviation(hitter_swings: Iterable[SwingRow], league_swings: Iterable[SwingRow],
                      min_swings: int = 30) -> dict[tuple[str, str], tuple[float, float]]:
    """Hitter minus league whiff rate and xwOBAcon per (pitch family, height) cell, from tracked swings."""
    def agg(rs):
        d: dict = {}
        for s in rs:
            fam = FAMILY_OF.get(s.pitch_type)
            if not fam:
                continue
            a = d.setdefault((fam, vert_region(s.z)), [0, 0, 0, 0.0])
            a[0] += 1
            a[1] += s.whiff
            if s.xwoba is not None:
                a[2] += 1
                a[3] += s.xwoba
        return d
    h, lg = agg(hitter_swings), agg(league_swings)
    out = {}
    for k, a in h.items():
        b = lg.get(k)
        if not b or a[0] < min_swings or b[0] < 200:
            continue
        dx = (a[3] / a[2] - b[3] / b[2]) if a[2] >= 15 and b[2] >= 50 else 0.0
        out[k] = (a[1] / a[0] - b[1] / b[0], dx)
    return out


@dataclass
class CoachLedger:
    """Accumulates (stated, tracked) pairs per coach and turns them into trust weights."""
    pairs: dict[str, list[tuple[float, float, float, float]]] = field(default_factory=lambda: defaultdict(list))

    def score(self, report: CoachReport, tracked: dict[tuple[str, str], tuple[float, float]]) -> int:
        """Record how a report compares with tracked deviations. Returns cells scored."""
        n = 0
        for cell, (sw, sc) in cell_signal(report).items():
            if cell in tracked:
                tw, tc = tracked[cell]
                self.pairs[report.coach_id].append((sw, tw, sc, tc))
                n += 1
        return n

    @staticmethod
    def _slope(pairs, i_s: int, i_t: int) -> float:
        num = sum(p[i_s] * p[i_t] for p in pairs)
        den = sum(p[i_s] ** 2 for p in pairs)
        return num / den if den else 0.0

    def trust(self, coach_id: str) -> tuple[float, float]:
        """(whiff trust, contact trust) in [0, 1]."""
        ps = self.pairs.get(coach_id, [])
        n = len(ps)
        out = []
        for i_s, i_t in ((0, 1), (2, 3)):
            slope = self._slope(ps, i_s, i_t) if n else PRIOR_TRUST
            t = (n * slope + PRIOR_STRENGTH * PRIOR_TRUST) / (n + PRIOR_STRENGTH)
            out.append(min(max(t, 0.0), 1.0))
        return out[0], out[1]


def merge_reports(reports: Iterable[CoachReport], ledger: CoachLedger, source: str = "") -> CoachProfile:
    """One profile for a hitter from all his reports, each tag scaled by its coach's trust."""
    tags = []
    for r in reports:
        tw, tc = ledger.trust(r.coach_id)
        tags += [CoachTag(t.family, t.vert, t.horiz, t.whiff_delta * tw, t.contact_delta * tc, t.confidence)
                 for t in r.tags]
    return CoachProfile(tuple(tags), source=source or "merged reports, trust-weighted", trust=1.0)
