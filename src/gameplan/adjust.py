"""In-game plan adjustments."""
from __future__ import annotations

from dataclasses import replace

from .models import Instruction, Plan, Rule

FASTBALL_TYPES = frozenset({"FF", "SI", "FC"})
VELO_TRIGGER_MPH = 2.5
INCHES_PER_MPH = 1.0     # lower GO zone floor 1 in per mph lost
MAX_SHIFT_IN = 4.0


def adjust_plan(plan: Plan, baseline_velo: float, current_velo: float) -> Plan:
    """If the pitcher's fastball has dropped >= 2.5 mph, extend the bottom of every fastball GO
    zone downward (slower pitch, more time, flatter VAA). One continuous rule rather than a
    step function: 3 mph -> 3 in, capped at 4 in. Applied from the baseline plan each time,
    never stacked on an already-adjusted plan."""
    drop = baseline_velo - current_velo
    if drop < VELO_TRIGGER_MPH:
        return plan
    shift = min(drop * INCHES_PER_MPH, MAX_SHIFT_IN)
    new_rules: list[Rule] = []
    for r in plan.rules:
        is_fb = r.pitch_types is None or bool(r.pitch_types & FASTBALL_TYPES)
        if r.instruction is Instruction.GO and is_fb:
            r = replace(r, zone=r.zone.shifted_down(shift))
        new_rules.append(r)
    note = f"velo drop {drop:.1f} mph: fastball GO zones extended down {shift:.1f} in"
    return replace(plan, rules=tuple(new_rules), notes=plan.notes + (note,))
