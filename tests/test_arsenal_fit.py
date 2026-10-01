from types import SimpleNamespace

import numpy as np

from gameplan.arsenal_fit import K, band, classify, hitter_fit, league_baseline, zone_bucket
from gameplan.savant import SwingRow
from gameplan.shape import PitchRow


class FlatZone:
    """Called-strike probability by x only: heart in the middle, chase far out."""

    def p(self, x, z, sb, st, strikes=None, balls=None):
        return np.where(np.abs(np.asarray(x, float)) < 0.4, 0.95, 0.02)


def swing(batter, pt, xw, whiff=False, aa=10.0, x=0.0, swing=True):
    return SwingRow(batter, "2025-07-01", pt, x, 2.5, 12.0, -5.0, 94.0, xw, whiff, x_away=x, attack_angle=aa, swing=swing)


def make_engine(his):
    lg = [swing("L%d" % (i % 20), pt, 0.35 if i % 3 else None, whiff=(i % 3 == 0)) for i, pt in zip(range(900), ["FF", "SL", "CH"] * 300)]
    ev = lg + his
    return SimpleNamespace(league_swings=[s for s in ev if s.swing], events=ev, zone=FlatZone(),
                           by_hitter={"H": his, **{"L%d" % i: [s for s in lg if s.batter == "L%d" % i] for i in range(20)}})


def starter_rows():
    return [PitchRow("P", "2025-06-01", t, 1, 94.0, 12.0, -3.0, -5.0) for t in ["FF"] * 6 + ["SL"] * 3 + ["CH"]]


def test_band_edges():
    assert band(-0.1) == "flat" and band(0) == "edge" and band(6) == "matched" and band(23.9) == "matched"
    assert band(24) == "edge" and band(27) == "steep" and band(None) == "unknown"


def test_zone_bucket():
    assert zone_bucket(0.95) == "heart" and zone_bucket(0.5) == "shadow" and zone_bucket(0.05) == "chase"


def test_hitter_with_no_swings_equals_league():
    eng = make_engine([])
    lg = league_baseline(eng)
    fit = hitter_fit(eng, lg, "H", starter_rows())
    for g in fit["groups"].values():
        assert abs(g["damage"] - g["league"]) < 1e-6                       # no swings: exactly the league group
        assert abs(g["idx"] - g["league"] / lg["overall"]) < 0.01          # index is group damage over his average swing


def test_damage_group_is_flagged_and_shrunk():
    his = [swing("H", "FF", 0.70, aa=12.0) for _ in range(200)] + [swing("H", "SL", 0.10, whiff=False, aa=4.0) for _ in range(200)]
    eng = make_engine(his)
    lg = league_baseline(eng)
    fit = hitter_fit(eng, lg, "H", starter_rows())
    ff, sl = classify(fit, "FF", "heart"), classify(fit, "SL", "heart")
    assert ff["cat"] == "damage" and sl["cat"] == "weak"
    league_ff = lg["groups"][("FB", "heart")]
    assert league_ff < ff["damage"] < 0.70            # pulled toward league, not all the way to his own average
    few = [swing("H", "FF", 0.70) for _ in range(4)]
    e2 = make_engine(few)
    lg2 = league_baseline(e2)
    f2 = hitter_fit(e2, lg2, "H", starter_rows())
    assert abs(f2["groups"]["FB|heart"]["damage"] - lg2["groups"][("FB", "heart")]) < 0.1   # 4 swings barely move him
    assert K == 40.0


def test_arsenal_table_expected_plane_fit():
    his = [swing("H", "FF", 0.40, aa=12.0) for _ in range(120)]
    eng = make_engine(his)
    fit = hitter_fit(eng, league_baseline(eng), "H", starter_rows())
    ff = next(t for t in fit["types"] if t["type"] == "FF")
    assert ff["n_swings"] == 120 and ff["vaa"] == -5.0
    assert ff["exp_vba"] is not None and 12.0 < ff["exp_vba"] < 20.0     # his attack angle (about 12, a little league) minus VAA -5
    assert ff["band"] == "matched"
