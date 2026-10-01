"""Can he damage what he swings at?  Hitter damage by pitch family and zone, and swing path against the starter's arsenal.

Damage per swing: xwOBA on contact for a ball in play, zero for a miss or a foul. It is a plain average over his swings, so a
hitter who whiffs a lot or fouls a lot scores lower on that pitch group. Nothing else is mixed in.

Groups: pitch family (fastball, breaking, offspeed) by zone bucket (heart, shadow, chase; the same buckets the development
targets use, from the called-strike model). A hitter has well under one swing behind any single zone cell, so groups, not cells.

Shrinkage: his group average is pulled toward the league group average with k = 40 swings (CHOICE, a plain pseudo-count; a
hitter with 40 swings in a group is half his own, half league). Every number shown carries its swing count.

Plane fit: vertical bat-ball angle (VBA) = attack angle minus the pitch's vertical approach angle (negative, so the angle grows
when the pitch comes down steeper). Bands come from the 2025 league table in docs/plane_match.txt, where whiff rate is lowest
between roughly 6 and 24 degrees and climbs steeply above 27 (36% to 80% whiffs); below 0 contact quality falls.
Descriptive, not a causal claim.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

import numpy as np

from .coach import FAMILY_OF

K = 40.0                      # CHOICE: pseudo-swings pulling a hitter's group toward the league group
DAMAGE_HI, DAMAGE_LO = 1.15, 0.85   # CHOICE: index versus his own average damage per swing
MATCH_LO, MATCH_HI, STEEP, FLAT = 6.0, 24.0, 27.0, 0.0   # DERIVED from docs/plane_match.txt
MIN_USAGE = 0.05
VBA_CENTER = 17.0             # same as traits_test.py
LAMBDA_PERSONAL = 150.0       # CHOICE, same as the pre-registered test: swings of pull toward the league whiff-versus-VBA curve
SWEET_TOL = 0.03              # CHOICE: his sweet band is where his predicted whiff rate is within 3 points of his own best
MIN_AA_SWINGS = 100
GRID = np.arange(0.0, 37.0, 1.0)      # 0 to 36 degrees: where the league table has thousands of swings per bin
LEAGUE_SAMPLE = 120000


def zone_bucket(p_cs: float) -> str:
    return "heart" if p_cs > 0.9 else "shadow" if p_cs >= 0.1 else "chase"


def band(vba: Optional[float]) -> str:
    """matched, edge, steep, flat or unknown."""
    if vba is None:
        return "unknown"
    if vba < FLAT:
        return "flat"
    if vba >= STEEP:
        return "steep"
    if MATCH_LO <= vba < MATCH_HI:
        return "matched"
    return "edge"


def _feats(v) -> np.ndarray:
    x = (np.asarray(v, float) - VBA_CENTER) / 10.0
    return np.column_stack([np.ones_like(x), x, x ** 2])


def _fit_logit(F, y, lam, prior, iters=30):
    w = prior.copy()
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(F @ w, -30, 30)))
        g = F.T @ (p - y) + lam * (w - prior)
        H = (F * (p * (1 - p))[:, None]).T @ F + lam * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w = w - step
        if np.abs(step).max() < 1e-7:
            break
    return w


def band_personal(vba: Optional[float], sweet) -> str:
    """His own band when he has one (matched inside it, steep or flat more than 3 degrees outside), else the league band."""
    if vba is None:
        return "unknown"
    if not sweet:
        return band(vba)
    lo, hi = sweet
    return "matched" if lo <= vba <= hi else "steep" if vba > hi + 3 else "flat" if vba < lo - 3 else "edge"


def damage(s) -> float:
    return float(s.xwoba) if (s.swing and s.xwoba is not None) else 0.0


def _buckets(zone, rows) -> list[str]:
    x = [s.x_away for s in rows]
    z = [s.z for s in rows]
    sb = [s.sz_bot or 1.5 for s in rows]
    st = [s.sz_top or 3.5 for s in rows]
    p = zone.p(x, z, sb, st, strikes=[s.strikes for s in rows], balls=[s.balls for s in rows])
    return [zone_bucket(v) for v in p]


def _shrink(n: int, mean: float, prior: float, k: float = K) -> float:
    return (k * prior + n * mean) / (k + n) if (n or k) else prior


def league_baseline(eng, seed: int = 7) -> dict:
    """League damage per swing by (family, bucket), and per pitch type: whiff, damage, swing rate, attack angle, matched share."""
    rng = np.random.default_rng(seed)
    pool = [s for s in eng.league_swings if s.x_away is not None and s.z is not None]
    idx = rng.choice(len(pool), min(LEAGUE_SAMPLE, len(pool)), replace=False)
    rows = [pool[i] for i in idx]
    acc = defaultdict(lambda: [0.0, 0])
    for s, b in zip(rows, _buckets(eng.zone, rows)):
        g = (FAMILY_OF.get(s.pitch_type, "OTHER"), b)
        acc[g][0] += damage(s)
        acc[g][1] += 1
    groups = {g: v[0] / v[1] for g, v in acc.items() if v[1] >= 50}
    overall = float(np.mean([damage(s) for s in rows]))
    seen = defaultdict(int)
    for s in eng.events:
        seen[s.pitch_type] += 1
    by_t = defaultdict(list)
    for s in eng.league_swings:
        by_t[s.pitch_type].append(s)
    types = {}
    for t, ss in by_t.items():
        aa = [s.attack_angle for s in ss if s.attack_angle is not None and s.vaa is not None]
        vba = [s.attack_angle - s.vaa for s in ss if s.attack_angle is not None and s.vaa is not None]
        types[t] = {"swing_rate": len(ss) / max(seen[t], 1), "whiff": float(np.mean([s.whiff for s in ss])),
                    "damage": float(np.mean([damage(s) for s in ss])),
                    "aa": float(np.mean(aa)) if aa else None,
                    "matched": float(np.mean([band(v) == "matched" for v in vba])) if vba else None}
    aa_rows = [s for s in eng.league_swings if s.attack_angle is not None and s.vaa is not None]
    beta = None
    if len(aa_rows) > 1000:
        beta = _fit_logit(_feats([s.attack_angle - s.vaa for s in aa_rows]), np.array([s.whiff for s in aa_rows], float), 1.0, np.zeros(3))
    return {"groups": groups, "overall": overall, "types": types, "beta": beta}


def hitter_fit(eng, lg: dict, h: str, starter_rows, min_group: int = 1) -> dict:
    """Per-hitter table against this starter's arsenal, plus group damage indexes used to label each swing."""
    mine = [s for s in eng.by_hitter[h]]
    sw = [s for s in mine if s.swing and s.x_away is not None and s.z is not None]
    his_avg = _shrink(len(sw), float(np.mean([damage(s) for s in sw])) if sw else lg["overall"], lg["overall"])
    grp = defaultdict(list)
    for s, b in zip(sw, _buckets(eng.zone, sw) if sw else []):
        grp[(FAMILY_OF.get(s.pitch_type, "OTHER"), b)].append(damage(s))
    groups = {}
    for g, lgm in lg["groups"].items():
        v = grp.get(g, [])
        d = _shrink(len(v), float(np.mean(v)) if v else lgm, lgm)
        idx = d / his_avg if his_avg > 0 else 1.0
        cat = "damage" if idx >= DAMAGE_HI else "weak" if idx <= DAMAGE_LO else "average"
        groups[f"{g[0]}|{g[1]}"] = {"n": len(v), "damage": round(d, 3), "idx": round(idx, 2), "cat": cat, "league": round(lgm, 3)}
    # personal sweet band: his whiff-versus-VBA curve, ridge toward the league curve (validated in docs/traits_test.txt)
    pers = [s for s in mine if s.swing and s.attack_angle is not None and s.vaa is not None]
    sweet, curve, center = None, None, None
    if lg.get("beta") is not None and len(pers) >= MIN_AA_SWINGS:
        bh = _fit_logit(_feats([s.attack_angle - s.vaa for s in pers]), np.array([s.whiff for s in pers], float), LAMBDA_PERSONAL, lg["beta"])
        G = _feats(GRID)
        ph, pl = 1 / (1 + np.exp(-(G @ bh))), 1 / (1 + np.exp(-(G @ lg["beta"])))
        j = int(np.argmin(ph))
        lo = hi = j
        while lo > 0 and ph[lo - 1] <= ph[j] + SWEET_TOL:
            lo -= 1
        while hi < len(GRID) - 1 and ph[hi + 1] <= ph[j] + SWEET_TOL:
            hi += 1
        sweet, center = [float(GRID[lo]), float(GRID[hi])], float(GRID[j])
        curve = {"vba": [float(v) for v in GRID[::2]], "his": [round(float(v), 3) for v in ph[::2]], "lg": [round(float(v), 3) for v in pl[::2]]}
    # arsenal
    tot = len(starter_rows) or 1
    use = defaultdict(list)
    for p in starter_rows:
        use[p.pitch_type].append(p)
    types = []
    for t, ps in sorted(use.items(), key=lambda kv: -len(kv[1])):
        if len(ps) / tot < MIN_USAGE or t not in lg["types"]:
            continue
        L = lg["types"][t]
        vaa = [p.vaa for p in ps if p.vaa is not None]
        velo = [p.velo for p in ps if p.velo is not None]
        seen = [s for s in mine if s.pitch_type == t]
        sws = [s for s in seen if s.swing]
        aas = [s.attack_angle for s in sws if s.attack_angle is not None]
        vbas = [s.attack_angle - s.vaa for s in sws if s.attack_angle is not None and s.vaa is not None]
        his_aa = _shrink(len(aas), float(np.mean(aas)) if aas else 0.0, L["aa"] if L["aa"] is not None else 0.0) if L["aa"] is not None else None
        exp_vba = (his_aa - float(np.mean(vaa))) if (his_aa is not None and vaa) else None
        types.append({
            "type": t, "usage": round(len(ps) / tot, 3), "velo": round(float(np.mean(velo)), 1) if velo else None,
            "vaa": round(float(np.mean(vaa)), 1) if vaa else None,
            "n_seen": len(seen), "n_swings": len(sws),
            "swing_rate": round(_shrink(len(seen), len(sws) / len(seen) if seen else 0.0, L["swing_rate"]), 3),
            "whiff": round(_shrink(len(sws), float(np.mean([s.whiff for s in sws])) if sws else 0.0, L["whiff"]), 3),
            "damage": round(_shrink(len(sws), float(np.mean([damage(s) for s in sws])) if sws else 0.0, L["damage"]), 3),
            "aa": round(his_aa, 1) if his_aa is not None else None,
            "exp_vba": round(exp_vba, 1) if exp_vba is not None else None,
            "band": band_personal(exp_vba, sweet),
            "matched": round(_shrink(len(vbas), float(np.mean([band(v) == "matched" for v in vbas])) if vbas else 0.0, L["matched"]), 3)
            if L["matched"] is not None else None,
            "league": {"swing_rate": round(L["swing_rate"], 3), "whiff": round(L["whiff"], 3), "damage": round(L["damage"], 3),
                       "aa": round(L["aa"], 1) if L["aa"] is not None else None,
                       "matched": round(L["matched"], 3) if L["matched"] is not None else None}})
    return {"swings": len(sw), "avg_damage": round(his_avg, 3), "league_damage": round(lg["overall"], 3),
            "groups": groups, "types": types, "sweet": sweet, "center": center, "n_aa": len(pers), "curve": curve}


def classify(fit: dict, pitch_type: str, bucket: str) -> Optional[dict]:
    g = fit["groups"].get(f"{FAMILY_OF.get(pitch_type, 'OTHER')}|{bucket}")
    return None if g is None else dict(g, family=FAMILY_OF.get(pitch_type, "OTHER"), zone=bucket)
