"""Illustrative approach styles built from an existing plan snapshot, for the coach mock-up and the
decision-relevance analysis. This is NOT the path generator. It hand-picks three styles so a coach can see
what "2-3 paths per count" would look like, and so we can measure whether such styles differ at all.

  VALUE    the plan as the model calls it (swing where swinging beats taking, take where the reverse).
  CONTACT  put the ball in play: drop GO cells whose predicted whiff on the swing is over CONTACT_MAX_WHIFF (the cap
           the CONTACT_FIRST situation policy uses) and add no-call cells where predicted whiff is at or under
           CONTACT_ADD_WHIFF and swinging is within CONTACT_ADD_DELTA of taking. Fewer misses, some quality given up.
  HUNT     sit on one pitch type and a few cells where the hitter's swing beats taking by the most; take
           everything else. With two strikes it reverts to VALUE (protect).

Descriptors (swing share, whiff on swings, contact quality on swings, value if followed) come from the same
location and swing-rate models the opportunity estimate uses. Tags are computed from the numbers, not typed."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .decision import CONTACT_FIRST_MAX_WHIFF
from .matchup import CELL_IN, X_RANGE, Z_RANGE, PlanSnapshot
from .opportunity import LocationModel, SwingRateModel, plan_opportunity

STYLES = ("VALUE", "CONTACT", "HUNT", "FULL")
CONTACT_MAX_WHIFF = CONTACT_FIRST_MAX_WHIFF
CONTACT_ADD_WHIFF = 0.15          # CHOICE for the mock-up, not fit
CONTACT_ADD_DELTA = -0.02         # swing minus take, wOBA scale; the edge of the "no strong call" band
HUNT_CELLS = 4
STEP = CELL_IN / 12.0


def _parse(key: str):
    pt, i, j = key.split("|")
    return pt, int(i), int(j)


def cell_region(i: int, j: int) -> str:
    """Plain-language region of a cell. x is feet away from the batter (negative = inside)."""
    x = X_RANGE[0] + (i + 0.5) * STEP
    z = Z_RANGE[0] + (j + 0.5) * STEP
    h = "in" if x < -0.35 else "away" if x > 0.35 else "middle"
    v = "low" if z < 2.0 else "high" if z > 3.0 else "middle"
    return f"{v}-{h}" if v != h else v


def style_cells(snap: PlanSnapshot, style: str, hunt_cells: int = HUNT_CELLS) -> dict:
    """The snapshot's cells with `cls` rewritten for this style. Cells keep their numbers."""
    cells = {k: dict(v) for k, v in snap.cells.items()}
    if style == "VALUE":
        return cells
    if style == "FULL":                                   # decided on every cell with the plate-appearance continuation (paths.full_policy)
        for c in cells.values():
            c["cls"] = c.get("full", c["cls"])
        return cells
    if style == "CONTACT":
        for c in cells.values():
            if c["cls"] == "GO" and c.get("whiff", 0.0) > CONTACT_MAX_WHIFF:
                c["cls"] = "CONDITIONAL"
            elif c["cls"] == "CONDITIONAL" and c.get("whiff", 1.0) <= CONTACT_ADD_WHIFF and c["delta"] >= CONTACT_ADD_DELTA \
                    and snap.situation.balls < 3:
                c["cls"] = "GO"
        return cells
    if style == "HUNT":
        if snap.situation.strikes >= 2:
            return cells                                    # protect: revert to the value plan
        go = [(k, c) for k, c in cells.items() if c["cls"] == "GO" and not c.get("low_support")]
        if not go:
            return cells
        mass = {pt: a["usage"] for pt, a in snap.arsenal.items()}
        by_type: dict[str, float] = {}
        for k, c in go:
            by_type[_parse(k)[0]] = by_type.get(_parse(k)[0], 0.0) + mass.get(_parse(k)[0], 0.0) * max(c["delta"], 0.0)
        target = max(by_type, key=by_type.get)
        pick = sorted((kc for kc in go if _parse(kc[0])[0] == target), key=lambda kc: -kc[1]["delta"])[:hunt_cells]
        keep = {k for k, _ in pick}
        for k, c in cells.items():
            c["cls"] = "GO" if k in keep else "NO_GO"
        return cells
    raise ValueError(style)


@dataclass(frozen=True)
class StyleSummary:
    style: str
    tags: tuple[str, ...]
    swing_share: float            # share of the starter's pitches landing in a GO cell
    whiff_on_swings: float
    contact_on_swings: float      # mean xwOBA on contact over GO cells
    value_per_100: float          # runs per 100 pitches if followed (upper bound; see opportunity.py)
    hunt_target: str = ""         # pitch type and region, HUNT only


def _mass_table(snap: PlanSnapshot, locations: LocationModel, stand: str | None):
    sit = snap.situation
    out = {}
    for pt, a in snap.arsenal.items():
        out[pt] = locations.mass(pt, stand, min(sit.strikes, 2)) * a["usage"]
    return out


def summarize(snap: PlanSnapshot, style: str, locations: LocationModel, swing_rate: SwingRateModel,
              stand: str | None, base_swing_share: float | None = None) -> StyleSummary:
    cells = style_cells(snap, style)
    variant = replace(snap, cells=cells)
    mass = _mass_table(snap, locations, stand)
    tot = sum(float(m.sum()) for m in mass.values()) or 1.0
    sw_mass = wh = xw = 0.0
    by_type_mass: dict[str, float] = {}
    for pt, m in mass.items():
        for n, (i, j, _, _) in enumerate(locations.cells):
            c = cells.get(f"{pt}|{i}|{j}")
            if c and c["cls"] == "GO":
                sw_mass += m[n]
                wh += m[n] * c.get("whiff", 0.0)
                xw += m[n] * c.get("xw", 0.0)
                by_type_mass[pt] = by_type_mass.get(pt, 0.0) + m[n]
    share = sw_mass / tot
    whiff = wh / sw_mass if sw_mass else 0.0
    contact = xw / sw_mass if sw_mass else 0.0
    opp = plan_opportunity(variant, locations, swing_rate, stand=stand)
    tags = _tags(share, whiff, contact, by_type_mass, base_swing_share)
    target = ""
    if style == "HUNT" and by_type_mass:
        pt = max(by_type_mass, key=by_type_mass.get)
        regions = sorted({cell_region(*_parse(k)[1:]) for k, c in cells.items()
                          if c["cls"] == "GO" and _parse(k)[0] == pt})
        target = f"{pt} {', '.join(regions)}"
    return StyleSummary(style, tags, share, whiff, contact, opp.runs_per_100_pitches, target)


def _tags(share: float, whiff: float, contact: float, by_type: dict, base_share: float | None) -> tuple[str, ...]:
    """Tags from numbers. Target: Hunt when one pitch type holds 80% or more of the swing mass, Cover when three or
    more share it, otherwise React. Aggression: Expand / Narrow when the swing share is 8 points above / below the
    VALUE plan's, else Standard. Risk: Contact when predicted whiff on swings is under 0.20, Damage when contact
    quality on swings is high, else Balanced."""
    tot = sum(by_type.values()) or 1.0
    top = max(by_type.values()) / tot if by_type else 0.0
    target = "Hunt" if top >= 0.8 and len(by_type) >= 1 else "Cover" if len(by_type) >= 3 else "React"
    if base_share is None:
        agg = "Standard"
    else:
        agg = "Expand" if share >= base_share + 0.08 else "Narrow" if share <= base_share - 0.08 else "Standard"
    risk = "Contact" if whiff < 0.20 else "Damage" if contact >= 0.40 else "Balanced"
    return (target, agg, risk)


def all_styles(snap: PlanSnapshot, locations: LocationModel, swing_rate: SwingRateModel,
               stand: str | None) -> dict[str, StyleSummary]:
    base = summarize(snap, "VALUE", locations, swing_rate, stand)
    out = {"VALUE": replace(base, tags=_tags(base.swing_share, base.whiff_on_swings, base.contact_on_swings,
                                             _go_type_mass(snap, locations, stand), None))}
    for st in ("CONTACT", "HUNT", "FULL"):
        out[st] = summarize(snap, st, locations, swing_rate, stand, base_swing_share=base.swing_share)
    return out


def _go_type_mass(snap, locations, stand):
    mass = _mass_table(snap, locations, stand)
    out: dict[str, float] = {}
    for pt, m in mass.items():
        for n, (i, j, _, _) in enumerate(locations.cells):
            c = snap.cells.get(f"{pt}|{i}|{j}")
            if c and c["cls"] == "GO":
                out[pt] = out.get(pt, 0.0) + m[n]
    return out


def call_difference(snap: PlanSnapshot, a: str, b: str, locations: LocationModel, stand: str | None) -> float:
    """Share of the starter's pitches (by location mass) where styles a and b make a different call."""
    ca, cb = style_cells(snap, a), style_cells(snap, b)
    mass = _mass_table(snap, locations, stand)
    tot = sum(float(m.sum()) for m in mass.values()) or 1.0
    diff = 0.0
    for pt, m in mass.items():
        for n, (i, j, _, _) in enumerate(locations.cells):
            k = f"{pt}|{i}|{j}"
            if k in ca and ca[k]["cls"] != cb[k]["cls"]:
                diff += m[n]
    return diff / tot
