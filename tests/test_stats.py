import numpy as np

from gameplan.stats import benjamini_hochberg, holm, interval, two_sided_p, two_way_draws


def test_two_way_interval_is_wider_than_one_way_when_pitchers_matter():
    rng = np.random.default_rng(0)
    nh, npi = 30, 6
    h = np.repeat(np.arange(nh), 40)
    p = rng.integers(0, npi, len(h))
    pitcher_effect = rng.normal(0, 1.0, npi)             # shared shocks: pitches vs the same pitcher move together
    y = pitcher_effect[p] + rng.normal(0, 1.0, len(h))
    stat = lambda w: float((w * y).sum() / w.sum())
    pt, draws = two_way_draws(h, p, stat, 400)
    one = np.array([float(np.mean(y[np.isin(h, rng.integers(0, nh, nh))])) for _ in range(400)])
    lo2, hi2 = interval(pt, draws)[1:]
    lo1, hi1 = np.percentile(one, [2.5, 97.5])
    assert (hi2 - lo2) > (hi1 - lo1)


def test_p_values_and_corrections():
    d = np.random.default_rng(1).normal(0.5, 0.1, 500)     # clearly positive
    assert two_sided_p(d, 0.0) < 0.01 and two_sided_p(d, 0.5) > 0.5
    p = {"a": 0.001, "b": 0.02, "c": 0.04, "d": 0.5}
    h, b = holm(p), benjamini_hochberg(p)
    assert h["a"] == 0.004 and h["b"] == 0.06 and h["d"] == 0.5 and b["a"] <= 0.004 + 1e-12
    assert all(h[k] >= p[k] and b[k] >= p[k] for k in p)
