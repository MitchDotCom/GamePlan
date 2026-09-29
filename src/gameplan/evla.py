"""Expected wOBA from exit velocity and launch angle, fit on MLB, for parks that record batted-ball
speed and angle but have no expected-stats model (MiLB feeds do not carry Savant's xwOBA).

Approximation only: the value is the smoothed average published-weight wOBA of MLB balls in play with
similar exit velocity and launch angle. Savant's xwOBA also uses sprint speed on some balls, so the
two differ; evaluate() reports how closely this tracks Savant's on held-out MLB balls. Values obtained
this way are flagged in the loader output (estimated_woba_source = evla)."""
from __future__ import annotations

import csv
import io
import json
import pathlib
from typing import Iterable

import numpy as np
from scipy.ndimage import gaussian_filter

from .decision import event_woba

EV_EDGES = np.arange(30.0, 122.0, 2.0)      # mph
LA_EDGES = np.arange(-60.0, 93.0, 3.0)      # degrees
DEFAULT_PATH = pathlib.Path(__file__).with_name("xwoba_evla_2025.json")


class EvLaXwoba:
    def __init__(self, grid: np.ndarray):
        self.grid = grid

    def __call__(self, ev, la):
        ev, la = np.asarray(ev, float), np.asarray(la, float)
        i = np.clip(np.searchsorted(EV_EDGES, ev, side="right") - 1, 0, len(EV_EDGES) - 2)
        j = np.clip(np.searchsorted(LA_EDGES, la, side="right") - 1, 0, len(LA_EDGES) - 2)
        return self.grid[i, j]

    def save(self, path: pathlib.Path = DEFAULT_PATH) -> None:
        path.write_text(json.dumps({"ev_edges": EV_EDGES.tolist(), "la_edges": LA_EDGES.tolist(),
                                    "grid": np.round(self.grid, 4).tolist()}))

    @classmethod
    def load(cls, path: pathlib.Path = DEFAULT_PATH) -> "EvLaXwoba":
        return cls(np.array(json.loads(path.read_text())["grid"]))


def _rows(texts: Iterable[str]):
    for t in texts:
        for r in csv.DictReader(io.StringIO(t)):
            if r.get("description") != "hit_into_play" or not r.get("launch_speed") or not r.get("launch_angle"):
                continue
            w = event_woba(r.get("events") or "")
            if w is None:
                continue
            yield float(r["launch_speed"]), float(r["launch_angle"]), w, r.get("estimated_woba_using_speedangle")


def fit(texts: Iterable[str], sigma: float = 1.0) -> EvLaXwoba:
    s = np.zeros((len(EV_EDGES) - 1, len(LA_EDGES) - 1))
    n = np.zeros_like(s)
    for ev, la, w, _ in _rows(texts):
        i = np.searchsorted(EV_EDGES, ev, side="right") - 1
        j = np.searchsorted(LA_EDGES, la, side="right") - 1
        if 0 <= i < s.shape[0] and 0 <= j < s.shape[1]:
            s[i, j] += w
            n[i, j] += 1
    ss, nn = gaussian_filter(s, sigma, mode="nearest"), gaussian_filter(n, sigma, mode="nearest")
    overall = s.sum() / max(n.sum(), 1)
    grid = np.where(nn > 1e-3, ss / np.maximum(nn, 1e-9), overall)
    # cells with almost no support fall back toward the overall mean rather than a noisy neighbour
    weight = np.clip(nn / (nn + 1.0), 0, 1)
    return EvLaXwoba(weight * grid + (1 - weight) * overall)


def evaluate(model: EvLaXwoba, texts: Iterable[str]) -> dict:
    """Agreement with Savant's xwOBA on balls in play (correlation, mean absolute error, bias)."""
    ev, la, x = [], [], []
    for e, l, _, sx in _rows(texts):
        if sx not in (None, ""):
            ev.append(e), la.append(l), x.append(float(sx))
    pred, x = model(np.array(ev), np.array(la)), np.array(x)
    return {"n": len(x), "corr": float(np.corrcoef(pred, x)[0, 1]), "mae": float(np.abs(pred - x).mean()),
            "bias": float((pred - x).mean())}
