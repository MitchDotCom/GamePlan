"""Plan generation: turn a predicted-xwOBA surface into Go / No-Go rules."""
from __future__ import annotations

from typing import Callable, Iterable

from .models import Hitter, Instruction, Pitcher, Plan, Rule, Zone

# Margins are relative to the hitter's own whiff-adjusted contact-quality baseline
# (hitter.baseline_cq), not absolute xwOBA points. Starting values; calibrate with gameplan.validate.
GO_REL = 0.15
NO_GO_REL = 0.20

# (x_ft, z_ft, pitch_type, ivb_in) -> predicted contact quality (whiff-adjusted) for this hitter.
XwobaModel = Callable[[float, float, str, float], float]


def grid_centers(x_range=(-1.25, 1.25), z_range=(1.0, 4.0), cell_in: float = 4.0):
    """(i, j, center_x, center_z) for every grid cell. Shared so callers can precompute
    predictions at exactly the centers generate_grid_plan will ask for."""
    step = cell_in / 12.0
    n_x = round((x_range[1] - x_range[0]) / step)
    n_z = round((z_range[1] - z_range[0]) / step)
    return [(i, j, x_range[0] + i * step + step / 2, z_range[0] + j * step + step / 2)
            for i in range(n_x) for j in range(n_z)]


def generate_grid_plan(
    hitter: Hitter,
    pitcher: Pitcher,
    xwoba_model: XwobaModel,
    pitch_types: Iterable[str],
    ivb_by_type: dict[str, float] | None = None,
    x_range: tuple[float, float] = (-1.25, 1.25),
    z_range: tuple[float, float] = (1.0, 4.0),
    cell_in: float = 4.0,
    go_rel: float = GO_REL,
    no_go_rel: float = NO_GO_REL,
) -> Plan:
    """One rule per grid cell per pitch type where the model is clearly good (GO) or clearly
    bad (NO_GO) for this hitter. Cells in between get no rule and fall to Plan.default.

    The model is the hard part; this only applies the thresholds. Feed it something fit on the
    hitter's own swings with enough sample per pitch type, or the plan is noise."""
    ivb_by_type = ivb_by_type or {}
    step = cell_in / 12.0
    rules: list[Rule] = []
    cells = grid_centers(x_range, z_range, cell_in)
    for pt in pitch_types:
        ivb = ivb_by_type.get(pt, 0.0)
        for i, j, cx, cz in cells:
            x0 = x_range[0] + i * step
            z0 = z_range[0] + j * step
            pred = xwoba_model(cx, cz, pt, ivb)
            if pred >= hitter.baseline_cq * (1 + go_rel):
                ins = Instruction.GO
            elif pred <= hitter.baseline_cq * (1 - no_go_rel):
                ins = Instruction.NO_GO
            else:
                continue
            rules.append(Rule(
                rule_id=f"{pt}_{i}_{j}_{ins.value}",
                instruction=ins,
                zone=Zone(x0, x0 + step, z0, z0 + step),
                pitch_types=frozenset({pt}),
            ))
    return Plan(hitter.player_id, pitcher.player_id, tuple(rules))
