import numpy as np

from gameplan.pilot import mde, n_per_arm, stepped_power


def test_mde_and_sample_size_are_inverses():
    e = mde(2500, 0.33)
    assert abs(n_per_arm(e, 0.33) - 2500) < 1
    assert abs(mde(2500, 0.21) - 0.0165) < 0.001          # matches the audit's 0.016 runs at 2,500 pitches


def test_stepped_power_rises_with_effect_and_volume():
    lo = stepped_power(10, 6, 200, 0.002, 0.33, sims=100)
    hi = stepped_power(10, 6, 200, 0.05, 0.33, sims=100)
    assert hi > lo and hi > 0.8
