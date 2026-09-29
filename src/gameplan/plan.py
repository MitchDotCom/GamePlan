"""Plan generation: turn a predicted-xwOBA surface into Go / No-Go rules."""
from __future__ import annotations

from typing import Callable, Iterable

from .models import Hitter, Instruction, Pitcher, Plan, Rule, Zone

GO_MARGIN = 0.040
NO_GO_MARGIN = 0.030

# (x_ft, z_ft, pitch_type, ivb_in) -> predicted xwOBA for this hitter on a swing.
XwobaModel = Callable[[float, float, str, float], float]


def generate_grid_plan(
    hitter: Hitter,
    pitcher: Pitcher,
    xwoba_model: XwobaModel,
    pitch_types: Iterable[str],
    ivb_by_type: dict[str, float] | None = None,
    x_range: tuple[float, float] = (-1.25, 1.25),
    z_range: tuple[float, float] = (1.0, 4.0),
    cell_in: float = 4.0,
) -> Plan:
    """One rule per grid cell per pitch type where the model is clearly good (GO) or clearly
    bad (NO_GO) for this hitter. Cells in between get no rule and fall to Plan.default.

    The model is the hard part; this only applies the thresholds. Feed it something fit on the
    hitter's own swings with enough sample per pitch type, or the plan is noise."""
    ivb_by_type = ivb_by_type or {}
    step = cell_in / 12.0
    rules: list[Rule] = []
    n_x = round((x_range[1] - x_range[0]) / step)
    n_z = round((z_range[1] - z_range[0]) / step)
    for pt in pitch_types:
        ivb = ivb_by_type.get(pt, 0.0)
        for i in range(n_x):
            for j in range(n_z):
                x0 = x_range[0] + i * step
                z0 = z_range[0] + j * step
                cx, cz = x0 + step / 2, z0 + step / 2
                pred = xwoba_model(cx, cz, pt, ivb)
                if pred >= hitter.baseline_xwoba + GO_MARGIN:
                    ins = Instruction.GO
                elif pred <= hitter.baseline_xwoba - NO_GO_MARGIN:
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
