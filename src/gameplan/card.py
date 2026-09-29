"""Plain-text plan card for a coach, and a demo CLI that builds one for a real matchup.

    python -m gameplan.card --batters data/b3 --pitchers data/p2 --hitter 665742 --starter 554430 \
        --tto 2 --balls 0 --strikes 2 --outs 1 --bases 001

Grid is the catcher's-eye view in batter-relative terms: columns run from inside to away, rows from
the top of the zone down. G = swing (GO), x = take (NO_GO), . = no call."""
from __future__ import annotations

import argparse
import glob
import pathlib

from .decision import PolicyBook, SituationConfig, SituationPolicy
from .matchup import (
    CELL_IN, X_RANGE, Z_RANGE, PlanSnapshot, Situation, arsenal_for_pa, build_plan, recommend_policy,
)
from .grid import grid_shape
from .models import Hitter
from .savant import parse_swings
from .zone import CalledStrikeModel
from .shape import ArsenalBasis, ContactModel, PitcherState, filter_starts, parse_pitches

SYMBOL = {"GO": "G", "NO_GO": "x", "CONDITIONAL": "."}


def render_card(snap: PlanSnapshot) -> str:
    n_x, n_z = grid_shape(X_RANGE, Z_RANGE, CELL_IN)
    sit = snap.situation
    lines = [f"plan {snap.plan_id}  {snap.level}  hitter {snap.hitter_id} vs starter {snap.pitcher_id}  mode {snap.mode.value}",
             f"count {sit.balls}-{sit.strikes}, {sit.outs} out, bases {''.join(str(int(b)) for b in sit.bases)}, "
             f"lead {sit.score_diff:+d}, inning {sit.inning}, TTO {sit.tto}"]
    lines += list(snap.notes)
    for pt, a in sorted(snap.arsenal.items(), key=lambda kv: -kv[1]["usage"]):
        lines.append("")
        lines.append(f"{pt}  usage {a['usage']:.0%}  {a['velo']:.1f} mph  IVB {a['ivb']:.1f}  HB {a['hb']:.1f}  VAA {a['vaa']:.1f}")
        lines.append("        in  ->  away")
        for j in range(n_z - 1, -1, -1):
            z_mid = Z_RANGE[0] + (j + 0.5) * CELL_IN / 12
            row = " ".join(SYMBOL[snap.cells[f"{pt}|{i}|{j}"]["cls"]] for i in range(n_x))
            lines.append(f"  {z_mid:4.1f} ft  {row}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batters", required=True)
    ap.add_argument("--pitchers", required=True)
    ap.add_argument("--hitter", required=True)
    ap.add_argument("--starter", required=True)
    ap.add_argument("--cutoff", default="9999")
    ap.add_argument("--tto", type=int, default=1)
    ap.add_argument("--pitch-count", type=int, default=0)
    ap.add_argument("--basis", default="TTO", choices=[b.value for b in ArsenalBasis])
    ap.add_argument("--balls", type=int, default=0)
    ap.add_argument("--strikes", type=int, default=0)
    ap.add_argument("--outs", type=int, default=0)
    ap.add_argument("--bases", default="000", help="on1B on2B on3B as 0/1, e.g. 001")
    ap.add_argument("--lead", type=int, default=0)
    ap.add_argument("--inning", type=int, default=1)
    ap.add_argument("--policy", default=None, choices=[p.value for p in SituationPolicy],
                    help="runner-on-third policy; omit to use the model's recommendation")
    a = ap.parse_args(argv)

    events = [s for f in sorted(glob.glob(str(pathlib.Path(a.batters) / "*.csv")))
              for s in parse_swings(open(f, encoding="utf-8-sig").read(), include_takes=True) if s.date < a.cutoff]
    zone = CalledStrikeModel([s for s in events if not s.swing])
    league = [s for s in events if s.swing]
    mine = [s for s in league if s.batter == a.hitter]
    model = ContactModel(mine, league, mode="shape")
    pitches = filter_starts(parse_pitches(open(pathlib.Path(a.pitchers) / f"{a.starter}_2025.csv", encoding="utf-8-sig").read()))
    stand = max(("R", "L"), key=lambda k: sum(s.stand == k for s in mine)) if mine else "R"
    bases = tuple(c == "1" for c in a.bases)
    sit = Situation(a.balls, a.strikes, a.outs, bases, a.lead, a.inning, a.tto)
    state = PitcherState(tto=a.tto, pitch_count=a.pitch_count)
    ars = arsenal_for_pa(pitches, a.cutoff, state, sit, stand, ArsenalBasis(a.basis))
    rec = recommend_policy(model, ars)
    print(f"model recommendation for runner on third: {rec[0].value} ({rec[2]})")
    pol = SituationPolicy(a.policy) if a.policy else rec[0]
    cfg = SituationConfig(runner_third_lt2=pol)
    snap = build_plan(model, Hitter(a.hitter), a.starter, ars, sit, game_id="demo", level="PA", config=cfg,
                      pitcher_state=state, zone_model=zone)
    print(render_card(snap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
