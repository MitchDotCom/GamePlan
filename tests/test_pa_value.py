"""The plate-appearance DP: all takes of called strikes end in a strikeout, all takes of balls end in a walk, and a sure
ball in play is worth its xwOBA in every count."""
import numpy as np

from gameplan.pa_value import COUNTS, solve


def _menus(ps, whiff, foul, xw, pcs):
    one = lambda v: np.array([v], float)
    return {c: {"m": one(1.0), "ps": one(ps), "whiff": one(whiff), "foul": one(foul), "xw": one(xw), "pcs": one(pcs)} for c in COUNTS}


def test_take_every_strike_is_strikeout():
    V = solve(_menus(0, 0, 0, 0.3, 1.0), walk=0.7, k_value=0.0)
    assert all(abs(v) < 1e-9 for v in V.values())


def test_take_every_ball_is_walk():
    V = solve(_menus(0, 0, 0, 0.3, 0.0), walk=0.7, k_value=0.0)
    assert all(abs(v - 0.7) < 1e-9 for v in V.values())


def test_sure_contact_is_worth_xwoba_in_every_count():
    V = solve(_menus(1, 0, 0, 0.35, 0.5), walk=0.7, k_value=0.0)
    assert all(abs(v - 0.35) < 1e-9 for v in V.values())


def test_foul_with_two_strikes_stays_in_the_count():
    V = solve(_menus(1, 0, 0.5, 0.4, 0.5), walk=0.7, k_value=0.0)
    assert abs(V[(0, 2)] - 0.4) < 1e-9          # fouls repeat until the ball is put in play
