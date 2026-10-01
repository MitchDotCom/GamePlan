"""Coach mock-up: one real 2025 MLB lineup against one real starter, built with the current engine.

Pregame: for each of the 9 hitters, every count, three illustrative approach styles (path_variants.py) plus the
hitter's development targets. Post-game: every pitch the lineup saw from that starter, scored against the plan in
force at that count and time through the order. Public Savant data only, fit only on games before the date.
Output is for showing a hitting coach and collecting feedback. It is not a validated product.

    python -m gameplan.mockup --league data/league --date 2025-08-19 --game 776685 --starter 669373 --out docs/mockup
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import pathlib
from collections import Counter, defaultdict

import numpy as np

from .coach import FAMILY_OF
from .decision import evs_np
from .matchup import CELL_IN, X_RANGE, Z_RANGE, Situation, build_plan, review_pitch
from .models import Action, Hitter, Pitch, Result, Swing
from .opportunity import LocationModel, SwingRateModel
from .path_variants import all_styles, call_difference, cell_region, style_cells
from .savant import SwingRow, fetch_csv, parse_swings
from .shape import ArsenalBasis, ContactModel, PitcherState, arsenal_for_state, filter_starts, parse_pitches
from .zone import CalledStrikeModel
from .constants import value as _const

COUNTS = [(b, s) for s in range(3) for b in range(4)]          # 12 counts
TTOS = (1, 2, 3)
STEP = CELL_IN / 12.0


# ---------------------------------------------------------------- data

def _files(league_dir: str):
    return sorted(glob.glob(str(pathlib.Path(league_dir) / "*.csv")))


def load_events(league_dir: str, before: str) -> list[SwingRow]:
    out = []
    for f in _files(league_dir):
        if pathlib.Path(f).stem >= before:
            continue
        out += parse_swings(open(f, encoding="utf-8-sig").read(), include_takes=True)
    return out


def load_pitcher_rows(league_dir: str, pitcher: str, before: str):
    rows = []
    for f in _files(league_dir):
        if pathlib.Path(f).stem >= before:
            continue
        rows += [p for p in parse_pitches(open(f, encoding="utf-8-sig").read()) if p.pitcher == pitcher]
    return filter_starts(rows)


def _flip(n: str) -> str:
    if "," in n:
        last, first = [x.strip() for x in n.split(",", 1)]
        return f"{first} {last}"
    return n


def game_lineup(league_dir: str, date: str, game_pk: str, starter: str):
    """Batters who faced `starter` in the game, by first appearance, with their names (the day files' player_name
    column is the batter's name)."""
    seen, names = [], {}
    for r in csv.DictReader(open(pathlib.Path(league_dir) / f"{date}.csv", encoding="utf-8-sig")):
        if r["game_pk"] != game_pk or r["pitcher"] != starter:
            continue
        if r["batter"] not in seen:
            seen.append(r["batter"])
            names[r["batter"]] = _flip(r.get("player_name", ""))
    return seen[:9], names


def pitcher_name(cache: str, pitcher: str) -> str:
    path = pathlib.Path(cache)
    if not path.exists():
        url = ("https://baseballsavant.mlb.com/leaderboard/custom?year=2025&type=pitcher&filter=&min=1"
               "&selections=p_game&chart=false&x=p_game&y=p_game&r=no&chartType=beeswarm&csv=true")
        try:
            path.write_text(fetch_csv(url), encoding="utf-8")
        except Exception:
            return f"Starter {pitcher}"
    for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
        if str(r["player_id"]) == pitcher:
            return _flip(r.get("last_name, first_name", ""))
    return f"Starter {pitcher}"


# ---------------------------------------------------------------- models and plans

class Engine:
    """Everything fit on games before the date; builds snapshots on demand and caches them."""

    def __init__(self, events: list[SwingRow], pitcher_rows, date: str, starter: str, _shared: "Engine | None" = None):
        self.date, self.starter = date, starter
        self.pitcher_rows = pitcher_rows
        self.locations = LocationModel(pitcher_rows)
        self._snaps = {}
        if _shared is not None:                       # same league fit, different starter
            for k in ("events", "league_swings", "league", "zone", "by_hitter", "_models", "_rates", "_group_loss"):
                setattr(self, k, getattr(_shared, k))
            return
        self.events = events
        league = [s for s in events if s.swing]
        self.league_swings = league
        self.league = ContactModel([], league, mode="shapecount")
        self.zone = CalledStrikeModel([s for s in events if not s.swing])
        self.by_hitter = defaultdict(list)
        for s in events:
            self.by_hitter[s.batter].append(s)
        self._models, self._rates, self._group_loss = {}, {}, {}

    def retarget(self, pitcher_rows, starter: str) -> "Engine":
        return Engine(self.events, pitcher_rows, self.date, starter, _shared=self)

    def model(self, h: str) -> ContactModel:
        if h not in self._models:
            self._models[h] = ContactModel.for_hitter([s for s in self.by_hitter[h] if s.swing], self.league)
        return self._models[h]

    def rate(self, h: str) -> SwingRateModel:
        if h not in self._rates:
            self._rates[h] = SwingRateModel(self.by_hitter[h], self.events)
        return self._rates[h]

    def hitter(self, h: str, name: str = "") -> Hitter:
        sw = [s for s in self.by_hitter[h] if s.swing]
        bip = [s.xwoba for s in sw if s.xwoba is not None]
        whiff = float(np.mean([s.whiff for s in sw])) if sw else 0.23
        xwc = float(np.mean(bip)) if bip else 0.35
        return Hitter(h, name, baseline_cq=(1 - whiff) * xwc, baseline_xwobacon=xwc)

    def snapshot(self, h: str, tto: int, b: int, s: int, stand: str, hitter: Hitter):
        key = (h, tto, b, s)
        if key not in self._snaps:
            sit = Situation(b, s, 0, (False, False, False), 0, 1, tto)
            state = PitcherState(tto=tto)
            ars = arsenal_for_state(self.pitcher_rows, self.date, state, ArsenalBasis.TTO, False,
                                    stand=stand, strikes=min(s, 2))
            self._snaps[key] = build_plan(self.model(h), hitter, self.starter, ars, sit, game_id="mockup", level="GAME",
                                          pitcher_state=state, apply_tto_effect=True, zone_model=self.zone)
        return self._snaps[key]


# ---------------------------------------------------------------- hitter profile and development targets

def _zone_bucket(p_cs: float) -> str:
    return "heart" if p_cs > 0.9 else "shadow" if p_cs >= 0.1 else "chase"


def _count_state(b: int, s: int) -> str:
    return "two strikes" if s == 2 else "ahead" if b > s else "behind" if s > b else "even"


def _decision_loss(eng: Engine, rows):
    """Per-pitch runs lost against the average-hitter model's better option, plus the group labels."""
    Q, _ = eng.league.query_swings(rows)
    p = eng.league.predict(Q, use_hitter=False)
    sb = np.array([s.sz_bot or 1.5 for s in rows])
    st = np.array([s.sz_top or 3.5 for s in rows])
    bal = np.array([s.balls for s in rows])
    stk = np.array([s.strikes for s in rows])
    p_cs = eng.zone.p(Q[:, 0], Q[:, 1], sb, st, strikes=stk, balls=bal)
    sw, tk = evs_np(p["whiff"], p["foul"], p["xw"], p_cs, bal, stk)
    swung = np.array([s.swing for s in rows])
    loss = np.maximum(np.maximum(sw, tk) - np.where(swung, sw, tk), 0.0) / _const("WOBA_SCALE_2025")
    groups = [(FAMILY_OF.get(s.pitch_type, "OTHER"), _zone_bucket(p_cs[k]), _count_state(s.balls, s.strikes))
              for k, s in enumerate(rows)]
    return loss, groups


def _league_group_loss(eng: Engine, n: int = 120000) -> dict:
    """Average loss rate per group over a fixed random sample of league pitches (what a typical hitter gives up)."""
    if not eng._group_loss:
        rng = np.random.default_rng(7)
        pool = [s for s in eng.events if s.x_away is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)]
        rows = [pool[i] for i in rng.choice(len(pool), min(n, len(pool)), replace=False)]
        loss, groups = _decision_loss(eng, rows)
        acc = defaultdict(lambda: [0.0, 0])
        for l, g in zip(loss, groups):
            acc[g][0] += l
            acc[g][1] += 1
        eng._group_loss.update({g: v[0] / v[1] for g, v in acc.items()})
    return eng._group_loss


def development_targets(eng: Engine, h: str, top: int = 3) -> dict:
    """Where the hitter's actual swing/take choices cost MORE than a typical hitter's do, by pitch family, zone and
    count state, against the better option in an average-hitter model (so his own tendencies are not graded against
    themselves). Ranked by excess runs lost per 100 of his pitches. Descriptive; needs 25+ pitches per group."""
    rows = [s for s in eng.by_hitter[h] if s.x_away is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)]
    if len(rows) < 150:
        return {"n_pitches": len(rows), "groups": []}
    loss, groups = _decision_loss(eng, rows)
    base = _league_group_loss(eng)
    acc = defaultdict(lambda: [0.0, 0])
    for l, g in zip(loss, groups):
        acc[g][0] += l
        acc[g][1] += 1
    n = len(rows)
    ranked = []
    for g, (tot, cnt) in acc.items():
        if cnt < 25 or g not in base:
            continue
        excess = (tot / cnt - base[g]) * cnt / n * 100          # runs per 100 of all his pitches
        ranked.append((g, excess, tot / cnt * 100, base[g] * 100, cnt))
    ranked.sort(key=lambda x: -x[1])
    return {"n_pitches": n, "runs_lost_per_100": float(loss.sum() / n * 100),
            "groups": [{"family": g[0], "zone": g[1], "count": g[2], "excess_per_100": round(e, 2),
                        "his_rate": round(r, 1), "typical_rate": round(t, 1), "n": c} for g, e, r, t, c in ranked[:top]]}


def profile(eng: Engine, h: str) -> dict:
    sw = [s for s in eng.by_hitter[h] if s.swing]
    bip = [s for s in sw if s.xwoba is not None]
    lg = eng.league_swings
    lg_whiff = float(np.mean([s.whiff for s in lg]))
    lg_xw = float(np.mean([s.xwoba for s in lg if s.xwoba is not None]))
    return {"swings": len(sw), "bip": len(bip),
            "whiff": round(float(np.mean([s.whiff for s in sw])), 3) if sw else None,
            "xwobacon": round(float(np.mean([s.xwoba for s in bip])), 3) if bip else None,
            "league_whiff": round(lg_whiff, 3), "league_xwobacon": round(lg_xw, 3),
            "support": "high" if len(sw) >= 800 else "medium" if len(sw) >= 300 else "thin"}


# ---------------------------------------------------------------- board

def _encode_cells(snap, cls_map: dict) -> dict:
    """pitch type -> string of codes in grid order (i major, j minor): G swing, x take, . no call."""
    n_x = round((X_RANGE[1] - X_RANGE[0]) / STEP)
    n_z = round((Z_RANGE[1] - Z_RANGE[0]) / STEP)
    sym = {"GO": "G", "NO_GO": "x", "CONDITIONAL": "."}
    out = {}
    for pt in snap.arsenal:
        out[pt] = "".join(sym[cls_map[f"{pt}|{i}|{j}"]["cls"]] for i in range(n_x) for j in range(n_z))
    return out


def _deltas(snap) -> dict:
    n_x = round((X_RANGE[1] - X_RANGE[0]) / STEP)
    n_z = round((Z_RANGE[1] - Z_RANGE[0]) / STEP)
    return {pt: [round(snap.cells[f"{pt}|{i}|{j}"]["delta"], 3) for i in range(n_x) for j in range(n_z)]
            for pt in snap.arsenal}


def build_board(eng: Engine, lineup: list[str], names: dict, stands: dict, starter_name: str) -> dict:
    hitters = []
    for order, h in enumerate(lineup, 1):
        hit = eng.hitter(h, names.get(h, f"Hitter {h}"))
        stand = stands[h]
        rec = {"order": order, "id": h, "name": hit.name, "stand": stand, "profile": profile(eng, h),
               "targets": development_targets(eng, h), "tto": {}}
        for tto in TTOS:
            counts = {}
            for b, s in COUNTS:
                snap = eng.snapshot(h, tto, b, s, stand, hit)
                styles = all_styles(snap, eng.locations, eng.rate(h), stand)
                counts[f"{b}-{s}"] = {
                    "arsenal": {pt: {"usage": round(a["usage"], 3), "velo": round(a["velo"], 1), "ivb": round(a["ivb"], 1),
                                     "hb": round(a["hb"], 1)} for pt, a in snap.arsenal.items()},
                    "delta": _deltas(snap),
                    "styles": {st: {"cells": _encode_cells(snap, style_cells(snap, st)),
                                    "tags": list(sm.tags), "swing_share": round(sm.swing_share, 3),
                                    "whiff": round(sm.whiff_on_swings, 3), "contact": round(sm.contact_on_swings, 3),
                                    "value_per_100": round(sm.value_per_100, 2), "target": sm.hunt_target}
                               for st, sm in styles.items()},
                    "differ": {"VALUE_vs_CONTACT": round(call_difference(snap, "VALUE", "CONTACT", eng.locations, stand), 3),
                               "VALUE_vs_HUNT": round(call_difference(snap, "VALUE", "HUNT", eng.locations, stand), 3)},
                    "plan_id": snap.plan_id,
                }
            rec["tto"][str(tto)] = counts
        hitters.append(rec)
    ars0 = eng.snapshot(lineup[0], 1, 0, 0, stands[lineup[0]], eng.hitter(lineup[0])).arsenal
    return {"starter": {"id": eng.starter, "name": starter_name, "arsenal_tto1_0_0": ars0,
                        "starts_before": len({p.game_pk for p in eng.pitcher_rows})},
            "date": eng.date, "model": "shapecount + 3-ball zone, TTO effect on", "hitters": hitters}


# ---------------------------------------------------------------- post-game review

_SWING_DESC = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"}


def _call(s: SwingRow) -> str:
    if s.swing:
        if s.whiff:
            return "SWINGING_STRIKE"
        return "IN_PLAY" if (s.xwoba is not None or s.woba is not None) else "FOUL"
    return {"strike": "CALLED_STRIKE", "ball": "BALL", "hbp": "HBP"}.get(s.take_call, "BALL")


def review_game(eng: Engine, game_rows: list[SwingRow], lineup: list[str], names: dict, stands: dict) -> dict:
    out = {}
    for h in lineup:
        hit = eng.hitter(h, names.get(h, f"Hitter {h}"))
        rows = sorted([s for s in game_rows if s.batter == h and s.pitcher == eng.starter and s.x_away is not None
                       and None not in (s.velo, s.ivb, s.vaa)], key=lambda s: (s.at_bat, s.pitch_no))
        recs, counts, dv_total = [], Counter(), 0.0
        for s in rows:
            tto = min(max(s.tto or 1, 1), 3)
            snap = eng.snapshot(h, tto, min(s.balls, 3), min(s.strikes, 2), stands[h], hit)
            in_zone = abs(s.x_away) <= 0.83 and (s.sz_bot or 1.5) <= s.z <= (s.sz_top or 3.5)
            res = Result(_call(s), xwoba=s.xwoba, in_zone=in_zone, is_hit=(s.woba is not None and s.woba >= 0.8))
            pitch = Pitch(f"{s.game_pk}-{s.at_bat}-{s.pitch_no}", s.pitch_type, s.x_away, s.z, s.velo, s.ivb, s.vaa)
            swing = Swing(s.attack_angle, s.bat_speed, s.squared_up) if s.swing else None
            rv = review_pitch(snap, hit, pitch, Action.SWING if s.swing else Action.TAKE, res, swing)
            ev = rv.evaluation
            counts[ev.process] += 1
            if ev.decision_value_runs is not None:
                dv_total += ev.decision_value_runs
            i = int((s.x_away - X_RANGE[0]) // STEP)
            j = int((s.z - Z_RANGE[0]) // STEP)
            recs.append({"pa": s.at_bat, "pitch": s.pitch_no, "count": f"{s.balls}-{s.strikes}", "tto": tto,
                         "type": s.pitch_type, "region": cell_region(i, j) if 0 <= i and 0 <= j else "off grid",
                         "action": "swing" if s.swing else "take", "result": res.call,
                         "call": ev.instruction.value, "process": ev.process, "label": rv.label.value,
                         "dv_runs": None if ev.decision_value_runs is None else round(ev.decision_value_runs, 3),
                         "flags": list(ev.flags)})
        scored = [r for r in recs if r["dv_runs"] is not None]
        out[h] = {"pitches": len(recs), "process": dict(counts), "decision_value_runs": round(dv_total, 2),
                  "best": sorted(scored, key=lambda r: -r["dv_runs"])[:3],
                  "worst": sorted(scored, key=lambda r: r["dv_runs"])[:3],
                  "good_decision_bad_result": [r for r in recs if r["process"] == "GOOD" and r["label"] == "FOLLOWED_PLAN"
                                               and r["result"] in ("SWINGING_STRIKE", "CALLED_STRIKE")][:3],
                  "all": recs}
    return out


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--date", required=True, help="game date; the engine is fit on days before it")
    ap.add_argument("--game", required=True)
    ap.add_argument("--starter", required=True)
    ap.add_argument("--out", default="docs/mockup")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lineup, names = game_lineup(a.league, a.date, a.game, a.starter)
    starter_name = pitcher_name(str(pathlib.Path(a.league).parent / "pitcher_names_2025.csv"), a.starter)
    print(f"starter {starter_name} ({a.starter}); lineup {lineup}")
    events = load_events(a.league, a.date)
    game_rows = [s for s in parse_swings(open(pathlib.Path(a.league) / f"{a.date}.csv", encoding="utf-8-sig").read(),
                                         include_takes=True) if s.game_pk == a.game]
    stands = {h: Counter(s.stand for s in game_rows if s.batter == h and s.stand).most_common(1)[0][0] for h in lineup}
    print(f"events before {a.date}: {len(events)}")
    eng = Engine(events, load_pitcher_rows(a.league, a.starter, a.date), a.date, a.starter)
    board = build_board(eng, lineup, names, stands, starter_name)
    board["review"] = review_game(eng, game_rows, lineup, names, stands)
    (out / "board.json").write_text(json.dumps(board, separators=(",", ":")), encoding="utf-8")
    from .mockup_html import render
    (out / "board.html").write_text(render(board), encoding="utf-8")
    print(f"wrote {out / 'board.json'} and {out / 'board.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
