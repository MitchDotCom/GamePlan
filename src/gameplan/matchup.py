"""Plan builder, versioned snapshots and pitch review.

A plan is built for one situation: (hitter, starter, time through order, count, base-out, score).
Pregame you build one per hitter per TTO at the neutral count; in game you rebuild per plate
appearance or per pitch. Every build is stored as an immutable snapshot with its inputs so a later
review can say exactly what the plan was when the hitter made his decision."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

from .decision import (
    DEFAULT, CountValues, SituationWeights, classify, p_called_strike, pitch_value, situation_weights,
    GO_DELTA, NO_GO_DELTA,
)
from .evaluate import evaluate_pitch
from .models import (
    Action, Evaluation, GameContext, Hitter, Instruction, Pitch, Pitcher, Plan, Quadrant, Result,
    Rule, Swing, Zone,
)
from .plan import grid_centers
from .shape import ArsenalPitch, ContactModel, raw_query

MODEL_VERSION = "0.3"
X_RANGE, Z_RANGE, CELL_IN = (-1.25, 1.25), (1.0, 4.0), 6.0


class PlanMode(str, Enum):
    COMPETE = "COMPETE"   # matchup-optimal plan for this starter, TTO and situation
    DEVELOP = "DEVELOP"   # hitter's own fixed damage zone vs a reference arsenal, situation-blind


@dataclass(frozen=True)
class Situation:
    balls: int = 0
    strikes: int = 0
    outs: int = 0
    bases: tuple[bool, bool, bool] = (False, False, False)
    score_diff: int = 0
    inning: int = 1
    tto: int = 1


@dataclass(frozen=True)
class PlanSnapshot:
    plan_id: str
    level: str                      # "GAME" (pregame card) or "PA" / "PITCH" (live)
    game_id: str
    hitter_id: str
    pitcher_id: str
    mode: PlanMode
    situation: Situation
    arsenal: dict                   # pitch_type -> ArsenalPitch as dict
    cells: dict                     # "FF|i|j" -> {"swing":..,"take":..,"delta":..,"cls":..}
    plan: Plan
    model_version: str = MODEL_VERSION
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        d = {
            "plan_id": self.plan_id, "level": self.level, "game_id": self.game_id,
            "hitter_id": self.hitter_id, "pitcher_id": self.pitcher_id, "mode": self.mode.value,
            "situation": asdict(self.situation), "arsenal": self.arsenal, "cells": self.cells,
            "model_version": self.model_version, "notes": list(self.notes),
        }
        return d


def _plan_id(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def build_plan(
    model: ContactModel,
    hitter: Hitter,
    pitcher_id: str,
    arsenal: dict[str, ArsenalPitch],
    situation: Situation = Situation(),
    game_id: str = "",
    level: str = "GAME",
    mode: PlanMode = PlanMode.COMPETE,
    cv: CountValues = DEFAULT,
    sz: tuple[float, float] = (1.5, 3.5),
    use_hitter: bool = True,
    go: float = GO_DELTA,
    no_go: float = NO_GO_DELTA,
) -> PlanSnapshot:
    """DEVELOP mode ignores count / base-out / score: it is the hitter's fixed damage zone against
    the reference arsenal you pass, evaluated at a 0-0 count."""
    if mode is PlanMode.DEVELOP:
        sit = Situation(tto=situation.tto)
        w = SituationWeights()
    else:
        sit = situation
        w = situation_weights(sit.outs, sit.bases, sit.score_diff, sit.inning)
    cells = grid_centers(X_RANGE, Z_RANGE, CELL_IN)
    step = CELL_IN / 12.0
    rules: list[Rule] = []
    cell_out: dict[str, dict] = {}
    for pt, a in arsenal.items():
        Q = [raw_query(model.mode, cx, cz, pt, a.velo, a.ivb, a.hb, a.vaa) for _, _, cx, cz in cells]
        pred = model.predict(Q, use_hitter=use_hitter)
        for n, (i, j, cx, cz) in enumerate(cells):
            p = {k: float(v[n]) for k, v in pred.items()}
            v = pitch_value(p, p_called_strike(cx, cz, *sz), sit.balls, sit.strikes, cv, w)
            cls = classify(v.delta, go, no_go)
            cell_out[f"{pt}|{i}|{j}"] = {"swing": round(v.swing_ev, 4), "take": round(v.take_ev, 4),
                                         "delta": round(v.delta, 4), "cls": cls}
            if cls == "CONDITIONAL":
                continue
            x0, z0 = X_RANGE[0] + i * step, Z_RANGE[0] + j * step
            rules.append(Rule(f"{pt}_{i}_{j}_{cls}", Instruction(cls), Zone(x0, x0 + step, z0, z0 + step),
                              frozenset({pt})))
    plan = Plan(hitter.player_id, pitcher_id, tuple(rules))
    ars = {pt: asdict(a) for pt, a in arsenal.items()}
    pid = _plan_id(level, game_id, hitter.player_id, pitcher_id, mode.value, asdict(sit), ars,
                   MODEL_VERSION, go, no_go, use_hitter)
    return PlanSnapshot(pid, level, game_id, hitter.player_id, pitcher_id, mode, sit, ars, cell_out, plan)


# ------------------------------------------------------------------ review

class ReviewLabel(str, Enum):
    FOLLOWED = "FOLLOWED_PLAN"
    HITTER_BEAT_MODEL = "HITTER_BEAT_MODEL"   # deviated, result good: candidate model misstep
    DEVIATION_COST = "DEVIATION_COST"         # deviated, result bad: hitter error
    UMPIRE = "UMPIRE_MISS"
    NO_COVERAGE = "PLAN_SILENT"               # plan gave no call


@dataclass(frozen=True)
class Review:
    snapshot_id: str
    evaluation: Evaluation
    label: ReviewLabel
    model_delta: Optional[float]      # snapshot's swing-minus-take for the cell, if covered
    note: str


def review_pitch(snap: PlanSnapshot, hitter: Hitter, pitch: Pitch, action: Action, result: Result,
                 swing: Optional[Swing] = None) -> Review:
    """Score a pitch against the plan in force when it was thrown and label what happened.

    One HITTER_BEAT_MODEL is not evidence the model is wrong; aggregate them by cell before acting."""
    sit = snap.situation
    ev = evaluate_pitch(snap.plan, hitter, pitch, action, result,
                        GameContext(balls=sit.balls, strikes=sit.strikes), swing)
    step = CELL_IN / 12.0
    i = int((pitch.x - X_RANGE[0]) // step)
    j = int((pitch.z - Z_RANGE[0]) // step)
    cell = snap.cells.get(f"{pitch.pitch_type}|{i}|{j}")
    delta = cell["delta"] if cell else None
    if ev.umpire_miss:
        label, note = ReviewLabel.UMPIRE, "decision was fine; the call was wrong"
    elif "no_plan_coverage" in ev.flags or delta is None:
        label, note = ReviewLabel.NO_COVERAGE, "pitch type or location outside the plan"
    elif ev.decision_score >= 75:
        label, note = ReviewLabel.FOLLOWED, "followed the plan"
    elif ev.quadrant is Quadrant.Q3_LUCKY_RESULT:
        label, note = ReviewLabel.HITTER_BEAT_MODEL, "left the plan and it worked; check the cell over more pitches"
    else:
        label, note = ReviewLabel.DEVIATION_COST, "left the plan and it did not work"
    return Review(snap.plan_id, ev, label, delta, note)
