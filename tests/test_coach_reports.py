import random

import pytest

from gameplan.coach_reports import (
    CoachLedger, CoachReport, cell_signal, load_reports_csv, merge_reports, tracked_deviation,
)
from gameplan.coach import CoachTag
from gameplan.savant import SwingRow

CSV = """report_id,coach_id,hitter_id,date,family,vert,horiz,whiff_delta,contact_delta,confidence,notes
r1,A,h1,2026-04-01,FB,HIGH,,0.10,-0.03,3,late on velo
r1,A,h1,2026-04-01,BRK,LOW,,-0.05,0.02,2,
r2,B,h1,2026-04-02,,,,0.02,0.0,1,general
"""


def test_csv_parse_and_cell_signal():
    reps = load_reports_csv(CSV)
    r1 = next(r for r in reps if r.report_id == "r1")
    assert len(r1.tags) == 2 and r1.coach_id == "A"
    sig = cell_signal(r1)
    assert sig[("FB", "HIGH")] == (0.10, -0.03) and ("OFF", "MID") not in sig
    r2 = next(r for r in reps if r.report_id == "r2")
    assert len(cell_signal(r2)) == 9                      # blank dimensions spread to every cell


def test_bad_rows_are_rejected():
    with pytest.raises(ValueError):
        load_reports_csv(CSV.replace("FB,HIGH", "XX,HIGH"))
    with pytest.raises(ValueError):
        load_reports_csv(CSV.replace(",3,late", ",5,late"))


def _swings(n, whiff_p, seed):
    rnd = random.Random(seed)
    return [SwingRow("h", "2025-05-01", "FF", 0, rnd.uniform(3.0, 3.6), 14, -5, 93,
                     None if (w := rnd.random() < whiff_p) else 0.3, w) for _ in range(n)]


def test_ledger_trusts_the_accurate_coach_more_than_the_wrong_one():
    league = _swings(4000, 0.25, 1)
    hitter = _swings(400, 0.35, 2)                         # truly +0.10 whiff on high fastballs
    tracked = tracked_deviation(hitter, league)
    good = CoachReport("g", "good", "h", "d", (CoachTag("FB", "HIGH", None, 0.10, 0.0, 3),))
    bad = CoachReport("b", "bad", "h", "d", (CoachTag("FB", "HIGH", None, -0.10, 0.0, 3),))
    led = CoachLedger()
    for _ in range(100):
        led.score(good, tracked)
        led.score(bad, tracked)
    assert led.trust("good")[0] > 0.8 and led.trust("bad")[0] < 0.1
    assert led.trust("new coach") == (0.3, 0.3)            # unscored coach starts at the prior


def test_merge_scales_by_trust():
    led = CoachLedger()
    r = CoachReport("r", "unknown", "h", "d", (CoachTag("FB", None, None, 0.10, 0.05, 3),))
    prof = merge_reports([r], led)
    assert abs(prof.tags[0].whiff_delta - 0.03) < 1e-9 and abs(prof.tags[0].contact_delta - 0.015) < 1e-9
