import random

import numpy as np

from gameplan.calibration import CountCalibration
from gameplan.savant import SwingRow


def _swings(n, seed):
    """Whiff rate is higher at two strikes than the count-blind model can know."""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        strikes = rnd.choice([0, 1, 2])
        whiff = rnd.random() < (0.35 if strikes == 2 else 0.20)
        out.append(SwingRow(f"h{i % 40}", "d", "FF", rnd.uniform(-1, 1), rnd.uniform(1.5, 3.5), 14, -5, 93,
                            None if whiff else 0.30, whiff, x_away=0.0, hb=0.0, balls=rnd.choice([0, 1]), strikes=strikes))
    return out


def test_fit_recovers_the_count_effect_and_apply_moves_predictions():
    rows = _swings(6000, 1)
    by = {}
    for s in rows:
        by.setdefault(s.batter, []).append(s)
    cal = CountCalibration.fit(by)
    two = cal.offsets[(0, 2)]["whiff"]
    zero = cal.offsets[(0, 0)]["whiff"]
    assert two > 0.05 and zero < -0.02                                     # two strikes: more whiffs than the pooled model says
    p = {"whiff": np.array([0.25, 0.25]), "foul": np.array([0.3, 0.3]), "xw": np.array([0.35, 0.35])}
    out = cal.apply(p, [0, 0], [2, 0])
    assert out["whiff"][0] > out["whiff"][1]
    assert CountCalibration.from_json(cal.to_json()).offsets.keys() == cal.offsets.keys()
