"""Count-specific recalibration of the swing model.

The swing model predicts whiff, foul and contact quality without knowing the count. Held-out league-wide
checks (docs/audit_checks_league.txt, C1) found small systematic gaps by count: swing value under-predicted
at 3 balls (+0.016) and at 2 strikes (+0.009). This fits an additive correction per (balls, strikes) to
the predicted whiff, foul and xwOBA-on-contact, from residuals of the league-only model on swings the
model did not see (two folds by hitter), and applies it before values are computed.

It is population-level: it moves every hitter the same amount at a given count. It does not make the
model count-aware for an individual hitter."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Iterable

import numpy as np

from .savant import SwingRow
from .shape import ContactModel

MIN_CELL = 300           # swings needed before a count's correction is trusted
SHRINK = 200.0           # residual sum divided by (n + SHRINK): thin counts are pulled toward no change


class CountCalibration:
    def __init__(self, offsets: dict[tuple[int, int], dict[str, float]]):
        self.offsets = offsets

    @classmethod
    def fit(cls, swings_by_hitter: dict[str, list[SwingRow]], mode: str = "shape", **model_kw) -> "CountCalibration":
        hitters = sorted(swings_by_hitter)
        fold = {h: i % 2 for i, h in enumerate(hitters)}
        acc: dict = defaultdict(lambda: {"n": 0, "w": 0.0, "f": 0.0, "nx": 0, "x": 0.0})
        for f in (0, 1):
            train = [s for h, rows in swings_by_hitter.items() if fold[h] != f for s in rows]
            model = ContactModel([], train, mode=mode, **model_kw)
            test = [s for h, rows in swings_by_hitter.items() if fold[h] == f for s in rows]
            Q, mask = model.query_swings(test)
            test = [s for s, k in zip(test, mask) if k]
            if not test:
                continue
            p = model.predict(Q, use_hitter=False)
            for k, s in enumerate(test):
                a = acc[(min(s.balls, 3), min(s.strikes, 2))]
                a["n"] += 1
                a["w"] += float(s.whiff) - p["whiff"][k]
                a["f"] += float((not s.whiff) and s.xwoba is None) - p["foul"][k]
                if s.xwoba is not None:
                    a["nx"] += 1
                    a["x"] += s.xwoba - p["xw"][k]
        offsets = {}
        for c, a in acc.items():
            if a["n"] >= MIN_CELL:
                offsets[c] = {"whiff": a["w"] / (a["n"] + SHRINK), "foul": a["f"] / (a["n"] + SHRINK),
                              "xw": a["x"] / (a["nx"] + SHRINK) if a["nx"] else 0.0}
        return cls(offsets)

    def apply(self, pred: dict[str, np.ndarray], balls, strikes) -> dict[str, np.ndarray]:
        """Add the count's correction to whiff, foul and xw predictions (arrays aligned with balls/strikes)."""
        b, s = np.minimum(np.asarray(balls, int), 3), np.minimum(np.asarray(strikes, int), 2)
        dw, df, dx = np.zeros(len(b)), np.zeros(len(b)), np.zeros(len(b))
        for (bb, ss), o in self.offsets.items():
            m = (b == bb) & (s == ss)
            dw[m], df[m], dx[m] = o["whiff"], o["foul"], o["xw"]
        out = dict(pred)
        out["whiff"] = np.clip(pred["whiff"] + dw, 0.0, 0.95)
        out["foul"] = np.clip(pred["foul"] + df, 0.0, 0.95)
        out["xw"] = np.clip(pred["xw"] + dx, 0.0, 2.1)
        over = np.maximum(out["whiff"] + out["foul"] - 0.98, 0.0)
        if over.any():
            sc = 1.0 - over / (out["whiff"] + out["foul"])
            out["whiff"], out["foul"] = out["whiff"] * sc, out["foul"] * sc
        return out

    def to_json(self) -> str:
        return json.dumps({f"{b}-{s}": o for (b, s), o in sorted(self.offsets.items())}, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "CountCalibration":
        return cls({tuple(map(int, k.split("-"))): v for k, v in json.loads(text).items()})
