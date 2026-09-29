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
    DEFAULT, CountValues, SituationConfig, SituationPolicy, SituationWeights, apply_situation, classify,
    p_called_strike, pitch_value, situation_weights, GO_DELTA, NO_GO_DELTA,
)
from .evaluate import evaluate_pitch
from .models import (
    Action, Evaluation, GameContext, Hitter, Instruction, Pitch, Pitcher, Plan, Quadrant, Result,
    Rule, Swing, Zone,
)
from .plan import grid_centers
from .shape import (
    TTO_EFFECT_2025, ArsenalBasis, ArsenalPitch, ContactModel, PitcherState, arsenal_for_state, cap_tto, raw_query,
)

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
    config: SituationConfig = SituationConfig(),
    pitcher_state: Optional[PitcherState] = None,
    apply_tto_effect: bool = False,
    zone_model=None,
) -> PlanSnapshot:
    """DEVELOP mode ignores count / base-out / score: it is the hitter's fixed damage zone against
    the reference arsenal you pass, evaluated at a 0-0 count."""
    if mode is PlanMode.DEVELOP:
        sit = Situation(tto=situation.tto)
        w = SituationWeights()
    else:
        sit = situation
        w = situation_weights(sit.outs, sit.bases, sit.score_diff, sit.inning, config)
    cv = apply_situation(cv, w)
    cells = grid_centers(X_RANGE, Z_RANGE, CELL_IN)
    step = CELL_IN / 12.0
    rules: list[Rule] = []
    cell_out: dict[str, dict] = {}
    for pt, a in arsenal.items():
        Q = [raw_query(model.mode, cx, cz, pt, a.velo, a.ivb, a.hb, a.vaa) for _, _, cx, cz in cells]
        pred = model.predict(Q, use_hitter=use_hitter)
        if apply_tto_effect and pitcher_state is not None and mode is PlanMode.COMPETE:
            dw, dx = TTO_EFFECT_2025[cap_tto(pitcher_state.tto) or 1]
            pred = dict(pred, whiff=pred["whiff"] + dw, xw=pred["xw"] + dx)
        for n, (i, j, cx, cz) in enumerate(cells):
            p = {k: float(v[n]) for k, v in pred.items()}
            p_cs = zone_model(cx, cz, sz[0], sz[1], sit.strikes) if zone_model is not None else p_called_strike(cx, cz, *sz)
            v = pitch_value(p, p_cs, sit.balls, sit.strikes, cv)
            cls = classify(v.delta, go, no_go)
            if cls == "GO" and w.max_whiff is not None and p["whiff"] > w.max_whiff:
                cls = "CONDITIONAL"   # contact-first: not worth a swing that likely misses
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
                   MODEL_VERSION, go, no_go, use_hitter, asdict(config),
                   asdict(pitcher_state) if pitcher_state else None, apply_tto_effect, zone_model is not None)
    notes = (f"situation weights: {asdict(w)}",) if mode is PlanMode.COMPETE else ("develop: situation-blind",)
    if pitcher_state:
        notes += (f"pitcher state: {asdict(pitcher_state)}, tto effect applied: {apply_tto_effect}",)
    return PlanSnapshot(pid, level, game_id, hitter.player_id, pitcher_id, mode, sit, ars, cell_out, plan,
                        notes=notes)


def arsenal_for_pa(pitches, before: str, state: PitcherState, sit: Situation, batter_stand: str,
                   basis: ArsenalBasis = ArsenalBasis.TTO, use_live_drift: bool = False):
    """The starter's arsenal for this plate appearance: shape by TTO or pitch count, usage by the
    batter's side and the strike count (fastballs are 62% of pitches at 0 strikes, 48% at 2)."""
    return arsenal_for_state(pitches, before, state, basis, use_live_drift,
                             stand=batter_stand or None, strikes=min(sit.strikes, 2))


ZONE_X, ZONE_Z = 0.83, (1.5, 3.5)
K_RISK_HIGH, K_RISK_MID = 0.27, 0.21   # provisional; league whiff per swing is about .23


def matchup_k_risk(model: ContactModel, arsenal: dict[str, ArsenalPitch], use_hitter: bool = True) -> float:
    """Usage-weighted predicted whiff per swing on pitches in the strike zone, for this hitter against
    this arsenal. This is the strikeout exposure that makes contact-first worth its cost."""
    cells = [c for c in grid_centers(X_RANGE, Z_RANGE, CELL_IN)
             if abs(c[2]) <= ZONE_X and ZONE_Z[0] <= c[3] <= ZONE_Z[1]]
    tot = wsum = 0.0
    for pt, a in arsenal.items():
        Q = [raw_query(model.mode, cx, cz, pt, a.velo, a.ivb, a.hb, a.vaa) for _, _, cx, cz in cells]
        tot += a.usage * float(model.predict(Q, use_hitter)["whiff"].mean())
        wsum += a.usage
    return tot / wsum if wsum else 0.0


def recommend_policy(model: ContactModel, arsenal: dict[str, ArsenalPitch]) -> tuple[SituationPolicy, float, str]:
    """Suggested policy for runner-on-third, < 2 outs, from this hitter's whiff exposure to this starter.
    A suggestion for the coach to accept or override, not a rule."""
    k = matchup_k_risk(model, arsenal)
    if k >= K_RISK_HIGH:
        pol = SituationPolicy.CONTACT_FIRST
        why = f"in-zone whiff exposure {k:.3f} is high: a strikeout is likely, put the ball in play"
    elif k >= K_RISK_MID:
        pol = SituationPolicy.STRONG
        why = f"in-zone whiff exposure {k:.3f} is above average: lean contact"
    else:
        pol = SituationPolicy.MILD
        why = f"in-zone whiff exposure {k:.3f} is low: the hitter can stay in his damage zone"
    return pol, k, why


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
    # Candidate "good decision that lost" definitions, recorded side by side. Which one the
    # organization adopts is an open research question; these are stored, not adjudicated.
    research_flags: tuple[str, ...] = ()


def review_pitch(snap: PlanSnapshot, hitter: Hitter, pitch: Pitch, action: Action, result: Result,
                 swing: Optional[Swing] = None) -> Review:
    """Score a pitch against the plan in force when it was thrown and label what happened.

    One HITTER_BEAT_MODEL is not evidence the model is wrong; aggregate them by cell before acting."""
    sit = snap.situation
    step = CELL_IN / 12.0
    i = int((pitch.x - X_RANGE[0]) // step)
    j = int((pitch.z - Z_RANGE[0]) // step)
    key = f"{pitch.pitch_type}|{i}|{j}"
    cell = snap.cells.get(key)
    ev = evaluate_pitch(cell, hitter, pitch, action, result, GameContext(balls=sit.balls, strikes=sit.strikes),
                        swing, cell_key=key if cell else None)
    delta = cell["delta"] if cell else None
    if ev.umpire_miss:
        label, note = ReviewLabel.UMPIRE, "decision was fine; the call was wrong"
    elif ev.process in ("UNSCORED", "NEUTRAL"):
        label, note = ReviewLabel.NO_COVERAGE, "no strong call for this pitch (outside the plan or too close to call)"
    elif ev.process == "GOOD":
        label, note = ReviewLabel.FOLLOWED, "took the action the model valued higher"
    elif ev.quadrant is Quadrant.Q3_LUCKY_RESULT:
        label, note = ReviewLabel.HITTER_BEAT_MODEL, "left the plan and it worked; check the cell over more pitches"
    else:
        label, note = ReviewLabel.DEVIATION_COST, "left the plan and it did not work"
    return Review(snap.plan_id, ev, label, delta, note, _research_flags(ev, action, result, hitter))


HARD_CONTACT_XWOBA = 0.500


def _research_flags(ev: Evaluation, action: Action, result: Result, hitter: Hitter) -> tuple[str, ...]:
    f = []
    good_dec = ev.process == "GOOD"
    call = result.call.upper()
    if good_dec and action is Action.TAKE and call == "CALLED_STRIKE":
        f.append("GOOD_TAKE_CALLED_STRIKE_UMP_MISS" if ev.umpire_miss else "GOOD_TAKE_CALLED_STRIKE_IN_ZONE")
    if good_dec and action is Action.SWING and call == "IN_PLAY" and result.xwoba is not None:
        if result.xwoba >= HARD_CONTACT_XWOBA and result.is_hit is False:
            f.append("GOOD_SWING_HARD_HIT_OUT")
        elif result.xwoba < hitter.baseline_xwobacon and result.is_hit:
            f.append("GOOD_SWING_LUCKY_HIT")
    if good_dec and action is Action.SWING and call in ("SWINGING_STRIKE", "FOUL"):
        f.append("GOOD_SWING_MISS_OR_FOUL")
    if ev.process == "BAD" and action is Action.TAKE and call == "BALL":
        f.append("BAD_TAKE_BUT_BALL")
    return tuple(f)
