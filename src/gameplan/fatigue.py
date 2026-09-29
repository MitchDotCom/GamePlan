"""What drives a starter's decline and the hitter's advantage: TTO, pitch count, batter familiarity,
live velocity drift, or rest? Separates them with regressions instead of assuming one.

Part A: within a pitcher-game, what moves fastball velo (pitch count vs TTO)?
Part B: what moves hitter results, after accounting for pitch location and shape?
        Residual = actual - league-model prediction (2-fold by hitter so no swing is scored by a
        model that saw its hitter), regressed on the state variables. Cluster bootstrap by starter.
Part C: does any of this differ for lower-velocity starters (the closest MLB analogue to a Single-A arm)?
"""
from __future__ import annotations

import numpy as np

from .savant import SwingRow
from .shape import FASTBALLS, ContactModel, PitchRow, cap_tto

RNG = np.random.default_rng(11)
PC_UNIT = 25.0


def state_index(pitch_by_pitcher: dict[str, list[PitchRow]]) -> dict[tuple, PitchRow]:
    return {(p.game_pk, p.at_bat, p.pitch_no): p for rows in pitch_by_pitcher.values() for p in rows}


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def _boot_ols(X, y, groups, n=300):
    """Coefficients and 95% CI, resampling groups (starters) with replacement."""
    beta = _ols(X, y)
    ug = np.unique(groups)
    idx_by = {g: np.where(groups == g)[0] for g in ug}
    draws = []
    for _ in range(n):
        pick = RNG.choice(ug, len(ug))
        ix = np.concatenate([idx_by[g] for g in pick])
        draws.append(_ols(X[ix], y[ix]))
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    return beta, lo, hi


def _fmt_rows(names, beta, lo, hi):
    return "\n".join(f"    {n:<22} {b:+.4f} [{l:+.4f}, {h:+.4f}]" for n, b, l, h in zip(names, beta, lo, hi))


def velo_drivers(pitch_by_pitcher: dict[str, list[PitchRow]], subset: str = "all") -> str:
    """Within pitcher-game fastball velo on pitch count and TTO, both demeaned within the game."""
    X, y, g = [], [], []
    for pid, rows in pitch_by_pitcher.items():
        by_game: dict[str, list[PitchRow]] = {}
        for r in rows:
            if r.pitch_type in FASTBALLS and r.velo and r.tto:
                by_game.setdefault(r.game_pk, []).append(r)
        for gr in by_game.values():
            if len(gr) < 20:
                continue
            v = np.array([r.velo for r in gr])
            f = np.array([[r.pitch_count / PC_UNIT, float(cap_tto(r.tto) == 2), float(cap_tto(r.tto) == 3)]
                          for r in gr])
            X.append(f - f.mean(0))
            y.append(v - v.mean())
            g += [pid] * len(gr)
    if not X:
        return "  (no data)"
    Xm, ym, gm = np.vstack(X), np.concatenate(y), np.array(g)
    beta, lo, hi = _boot_ols(Xm, ym, gm)
    return (f"  fastball velo (mph), within pitcher-game, {subset}: {len(ym)} fastballs\n"
            + _fmt_rows(["per 25 pitches", "TTO2 (vs TTO1)", "TTO3+ (vs TTO1)"], beta, lo, hi))


def residual_frame(swings_vs_starters: list[SwingRow], all_swings_by_hitter: dict[str, list[SwingRow]],
                   state: dict[tuple, PitchRow], mode: str = "shape"):
    """Rows of (starter, whiff_resid, xw_resid or nan, state features) for swings vs starters."""
    hitters = sorted(all_swings_by_hitter)
    fold = {h: i % 2 for i, h in enumerate(hitters)}
    models = {}
    for f in (0, 1):
        train = [s for h, rows in all_swings_by_hitter.items() if fold[h] != f for s in rows]
        models[f] = ContactModel([], train, mode=mode)
    out = []
    for f in (0, 1):
        rows = [s for s in swings_vs_starters if fold.get(s.batter) == f]
        Q, mask = models[f].query_swings(rows)
        rows = [s for s, k in zip(rows, mask) if k]
        if not rows:
            continue
        p = models[f].predict(Q, use_hitter=False)
        for k, s in enumerate(rows):
            st = state.get((s.game_pk, s.at_bat, s.pitch_no))
            if st is None or not st.tto:
                continue
            xr = (s.xwoba - p["xw"][k]) if s.xwoba is not None else np.nan
            out.append((s.pitcher, float(s.whiff) - p["whiff"][k], xr, st))
    return out


SPECS = {
    "TTO only": ["tto"],
    "pitch count only": ["pc"],
    "pitch count + TTO": ["pc", "tto"],
    "batter familiarity (prior PAs) only": ["prior"],
    "pitch count + TTO + rest": ["pc", "tto", "rest"],
    "pitch count + TTO + FB drift": ["pc", "tto", "drift"],
}
_COLS = {
    "pc": (["pitch count /25"], lambda st: [st.pitch_count / PC_UNIT]),
    "tto": (["TTO2", "TTO3+"], lambda st: [float(cap_tto(st.tto) == 2), float(cap_tto(st.tto) == 3)]),
    "prior": (["prior PA = 1", "prior PA >= 2"],
              lambda st: [float((st.prior_pa or 0) == 1), float((st.prior_pa or 0) >= 2)]),
    "rest": (["rest days /5"],
             lambda st: [min(st.days_rest if st.days_rest is not None else 5.0, 10.0) / 5.0]),
    "drift": (["FB drift (mph)"], lambda st: [st.fb_delta if st.fb_delta is not None else 0.0]),
}


def collinearity(frame) -> str:
    tto = np.array([cap_tto(r[3].tto) for r in frame], float)
    pa = np.array([min(r[3].prior_pa or 0, 2) for r in frame], float)
    pc = np.array([r[3].pitch_count for r in frame], float)
    return (f"  corr(TTO, prior PAs) = {np.corrcoef(tto, pa)[0, 1]:.2f}, "
            f"corr(TTO, pitch count) = {np.corrcoef(tto, pc)[0, 1]:.2f}")


def outcome_drivers(frame, title: str, specs=None) -> str:
    """Regress residuals on state under several specifications, so collinear variables (TTO, prior
    PAs, pitch count) are compared rather than entered together blindly."""
    specs = specs or ["TTO only", "pitch count only", "pitch count + TTO", "batter familiarity (prior PAs) only",
                      "pitch count + TTO + rest", "pitch count + TTO + FB drift"]
    out = [f"  {title}: {len(frame)} swings vs starters; " + collinearity(frame).strip()]
    for spec in specs:
        keys = SPECS[spec]
        rows = [r for r in frame if not ("drift" in keys and r[3].fb_delta is None)]
        if len(rows) < 500:
            continue
        names = ["const"] + [n for k in keys for n in _COLS[k][0]]
        X = np.array([[1.0] + [v for k in keys for v in _COLS[k][1](r[3])] for r in rows])
        gm = np.array([r[0] for r in rows])
        out.append(f"   [{spec}]")
        for label, col in (("whiff residual", 1), ("xwOBAcon residual", 2)):
            y = np.array([r[col] for r in rows])
            ok = ~np.isnan(y)
            beta, lo, hi = _boot_ols(X[ok], y[ok], gm[ok], n=200)
            out.append(f"     {label} (n={int(ok.sum())})")
            out.append(_fmt_rows(names[1:], beta[1:], lo[1:], hi[1:]).replace("\n    ", "\n      ").replace("    ", "      ", 1))
    return "\n".join(out)


def run(pitch_by_pitcher, events_by_hitter, cutoff: str | None = None) -> str:
    """Full Part A / B / C report. Pass swings only (swing=True rows)."""
    state = state_index(pitch_by_pitcher)
    sw_by_h = {b: [s for s in r if s.swing] for b, r in events_by_hitter.items()}
    vs = [s for rows in sw_by_h.values() for s in rows if (s.game_pk, s.at_bat, s.pitch_no) in state]
    lines = ["\n== Test 5: what drives starter decline and hitter advantage? (pitch count, TTO, familiarity, drift, rest)"]
    lines.append(" A. Fastball velocity within a start")
    lines.append(velo_drivers(pitch_by_pitcher))
    velos = {pid: np.mean([p.velo for p in rows if p.pitch_type in FASTBALLS and p.velo] or [np.nan])
             for pid, rows in pitch_by_pitcher.items()}
    med = np.nanmedian(list(velos.values()))
    slow = {p: r for p, r in pitch_by_pitcher.items() if velos[p] < med}
    fast = {p: r for p, r in pitch_by_pitcher.items() if velos[p] >= med}
    lines.append(velo_drivers(slow, f"slower half (FB < {med:.1f})"))
    lines.append(velo_drivers(fast, f"faster half (FB >= {med:.1f})"))
    frame = residual_frame(vs, sw_by_h, state)
    lines.append(" B. Hitter results beyond location and shape")
    lines.append(outcome_drivers(frame, "all starters"))
    lines.append(" C. Lower-velocity vs higher-velocity starters")
    slow_ids, fast_ids = set(slow), set(fast)
    lines.append(outcome_drivers([r for r in frame if r[0] in slow_ids], f"slower half (FB < {med:.1f})"))
    lines.append(outcome_drivers([r for r in frame if r[0] in fast_ids], f"faster half (FB >= {med:.1f})"))
    return "\n".join(lines)
