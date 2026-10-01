import numpy as np

from gameplan.savant import SwingRow
from gameplan.swing_traits import HitterTraits, LeagueTraits


def swings(n, seed, slope=0.0, shift=0.0):
    """Bat speed falls 1 mph per strike for everyone; this hitter's attack angle also changes by `slope` degrees from a low
    to a high pitch and his bat speed is `shift` mph above the league."""
    rnd = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        z = rnd.uniform(1.4, 3.6)
        k = int(rnd.integers(0, 3))
        zr = (z - 1.5) / 2.0
        out.append(SwingRow("h", "2025-05-01", "FF", rnd.normal(0, 0.6), z, 14.0, -4.5, rnd.normal(93, 3), None, False,
                            x_away=rnd.normal(0, 0.6), hb=-5.0, strikes=k, sz_bot=1.5, sz_top=3.5,
                            bat_speed=71 - 1.0 * k + shift + rnd.normal(0, 3),
                            swing_length=7.2 + rnd.normal(0, 0.4),
                            attack_angle=10 - 6.0 * (zr - 0.5) + slope * (zr - 0.5) + rnd.normal(0, 4), tilt=30 + rnd.normal(0, 5)))
    return out


def test_league_model_recovers_the_count_and_height_effects():
    lg = LeagueTraits(swings(4000, 1))
    X = np.zeros((2, 9)); X[:, 0] = 1.0
    X[1, 7] = 1.0                                                            # two strikes
    assert -2.6 < (lg.predict(X, "bat_speed")[1] - lg.predict(X, "bat_speed")[0]) < -1.4
    hi = np.zeros((1, 9)); hi[0, [0, 1]] = [1.0, 0.3]
    lo = np.zeros((1, 9)); lo[0, [0, 1]] = [1.0, -0.3]
    assert lg.predict(lo, "attack_angle")[0] > lg.predict(hi, "attack_angle")[0] + 2.0   # steeper on low pitches


def test_hitter_deviation_is_learned_and_shrunk_when_the_sample_is_small():
    lg = LeagueTraits(swings(4000, 1))
    big = HitterTraits.fit(swings(600, 2, slope=-8.0, shift=3.0), lg)
    small = HitterTraits.fit(swings(15, 3, slope=-8.0, shift=3.0), lg)
    other = swings(200, 4)
    e_big, keep = big.expected_for(other)
    e_lg = lg.predict(np.array([__import__("gameplan.swing_traits", fromlist=["context_row"]).context_row(other[k]) for k in keep]), "bat_speed")
    assert 2.0 < float(np.mean(e_big["bat_speed"] - e_lg)) < 3.6                  # most of his +3 mph
    e_small, _ = small.expected_for(other)
    assert abs(float(np.mean(e_small["bat_speed"] - e_lg))) < abs(float(np.mean(e_big["bat_speed"] - e_lg)))
    prof = big.profile()["attack_angle"]
    assert prof["low"] > prof["high"] and 0.8 < prof["kept"] < 1.0
