"""The plane term: a whiff-risk shift from the league whiff-versus-VBA curve evaluated at the hitter's EXPECTED attack angle.

Adopted after the pre-registered test (docs/traits_test_v2.txt, block PLANE: beats the full kernel model on whiffs in 2025 and 2024). For a pitch
in a given context (location, speed, break, approach angle, count) the hitter's expected attack angle is the league least-squares prediction plus
his shrunk deviation (swing_traits.HitterTraits). The expected vertical bat-ball angle is that minus the pitch's approach angle. The league curve
at that angle (a quadratic in the angle, centered at 17 degrees) is standardized and scaled by one coefficient fitted on held-out kernel
predictions. The shift is added to the logit of the kernel's whiff probability.

Not used: his personal curve shape (adds nothing once his expected angle is in), bat speed, swing length (fail the test). Damage is untouched.

    python -m gameplan.plane_term --b25 data/b3 --pitchers data/p2 --cutoff 2025-07-01 --out src/gameplan/plane_term_2025.json"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

from .swing_traits import HitterTraits, LeagueTraits, _design
from .traits_test import VBA_CENTER, _fit_logit, _vba_feats

DEFAULT_PATH = pathlib.Path(__file__).with_name("plane_term_2025.json")


def league_curve(league_train) -> np.ndarray:
    ltr = [s for s in league_train if s.attack_angle is not None and s.vaa is not None]
    return _fit_logit(_vba_feats([s.attack_angle for s in ltr], [s.vaa for s in ltr]), np.array([s.whiff for s in ltr], float),
                      np.zeros(len(ltr)), lam=1.0)


class PlaneTerm:
    """Parameters: beta (league curve), mu, sd, w (standardization and coefficient). Per hitter: bind(traits, zone) -> shift(Q)."""

    def __init__(self, beta, mu: float, sd: float, w: float, league: LeagueTraits, b: float = 0.0):
        self.beta, self.mu, self.sd, self.w, self.b, self.league = np.asarray(beta, float), mu, sd, w, b, league

    @classmethod
    def load(cls, league: LeagueTraits, path=DEFAULT_PATH):
        p = pathlib.Path(path)
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        return cls(d["beta"], d["mu"], d["sd"], d["w"], league, d.get("b", 0.0))

    def z(self, raw: np.ndarray, traits: HitterTraits | None, zone=(1.5, 3.5)) -> np.ndarray:
        """Curve value at the expected angle. raw rows are shapecount queries: x_away, z, velo, ivb, hb, vaa, balls, strikes."""
        raw = np.asarray(raw, float).reshape(-1, 8)
        zr = (raw[:, 1] - zone[0]) / max(zone[1] - zone[0], 0.5)
        strikes, balls = raw[:, 7], raw[:, 6]
        X = np.column_stack([np.ones(len(raw)), zr - 0.5, (zr - 0.5) ** 2, raw[:, 0], (raw[:, 2] - 90.0) / 5.0, (raw[:, 3] - 12.0) / 8.0,
                             (strikes == 1).astype(float), (strikes >= 2).astype(float), (balls >= 2).astype(float)])
        aa = traits.expected(X, "attack_angle") if traits is not None else self.league.predict(X, "attack_angle")
        return _vba_feats(aa, raw[:, 5]) @ self.beta

    def shift(self, raw, traits: HitterTraits | None, zone=(1.5, 3.5)) -> np.ndarray:
        return self.b + self.w * (self.z(raw, traits, zone) - self.mu) / self.sd

    @staticmethod
    def apply(whiff: np.ndarray, shift: np.ndarray) -> np.ndarray:
        p = np.clip(whiff, 1e-4, 1 - 1e-4)
        return 1.0 / (1.0 + np.exp(-(np.log(p / (1 - p)) + shift)))


def main(argv=None) -> int:
    from .shape import raw_swing
    from .traits_test import build_rows
    from .validate_mlb import load_batters, load_start_keys
    ap = argparse.ArgumentParser()
    ap.add_argument("--b25", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--cutoff", default="2025-07-01")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    batters = load_batters(a.b25)
    rows = build_rows(batters, a.cutoff, load_start_keys(a.pitchers))
    z = np.concatenate([r["F"][:, 6] for r in rows])
    y = np.concatenate([r["whiff"] for r in rows])
    p0 = np.concatenate([r["p_whiff"] for r in rows])
    mu, sd = float(z.mean()), float(z.std() + 1e-9)
    b, w = (float(v) for v in _fit_logit(np.column_stack([np.ones(len(z)), (z - mu) / sd]), y, np.log(p0 / (1 - p0)), lam=1e-6))
    league_train = [s for r in batters.values() for s in r if s.swing and s.date < a.cutoff]
    beta = league_curve(league_train)
    pathlib.Path(a.out).write_text(json.dumps({"beta": beta.tolist(), "mu": mu, "sd": sd, "w": w, "b": b, "n_swings": int(len(y)),
                                               "cutoff": a.cutoff, "center_deg": VBA_CENTER}, indent=1))
    p1 = PlaneTerm.apply(p0, b + w * (z - mu) / sd)
    ll = lambda p: float(-(y * np.log(np.clip(p, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1))).mean())
    cal = lambda p: float(np.polyfit(np.log(p / (1 - p)), y, 1)[0])
    print(f"fitted on {len(y)} held-out swings: b={b:+.4f}, w={w:+.4f} (per sd of the curve value), mu={mu:.4f}, sd={sd:.4f}")
    print(f"whiff log-loss {ll(p0):.5f} -> {ll(p1):.5f} (in-sample for the one coefficient; out-of-fold gain is in traits_test_v2.txt)")
    print(f"mean predicted whiff {p0.mean():.4f} -> {p1.mean():.4f}, observed {y.mean():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
