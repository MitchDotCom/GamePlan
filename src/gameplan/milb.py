"""Adapter from an organization's pitch-tracking export (TrackMan, Hawk-Eye, other) to the Savant-style
CSV the rest of the code reads.

Principles from the audit:
  * Nothing is dropped or guessed silently. Unmapped values raise (or are counted and reported).
  * Units are declared, converted, and then checked against MLB distributions, because a unit error
    (horizontal break in feet read as inches) already went unnoticed once.
  * Different systems measure differently; per-system offsets come from the DataProfile and are
    estimated from paired pitches with estimate_offsets, not assumed.
  * Expected wOBA is filled from exit velocity and launch angle (evla.py) only when the export has no
    expected-stats field, and is flagged.

You supply a ColumnMap (JSON) naming which of your columns is which canonical field. See
examples/milb_columnmap_example.json; its source column names are placeholders, not a claim about any
vendor's actual export."""
from __future__ import annotations

import csv
import io
import json
import math
import pathlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .bulk import KEEP
from .evla import EvLaXwoba
from .profiles import DataProfile

REQUIRED = ["game_id", "date", "batter_id", "pitcher_id", "stand", "p_throws", "balls", "strikes",
            "at_bat", "pitch_no", "inning", "pitch_type", "velo", "plate_x", "plate_z", "call"]
OPTIONAL = ["sz_top", "sz_bot", "ivb", "hb", "approach_angle", "vy0", "vz0", "ay", "az", "launch_speed",
            "launch_angle", "bat_speed", "swing_length", "attack_angle", "event", "outs", "on_1b", "on_2b",
            "on_3b", "bat_score", "fld_score", "inning_topbot", "expected_woba"]
EXTRA_COLUMNS = ["approach_angle", "estimated_woba_source"]
LENGTH_TO_FT = {"ft": 1.0, "in": 1 / 12.0, "cm": 0.0328084, "m": 3.28084}
SPEED_TO_MPH = {"mph": 1.0, "kph": 0.621371, "mps": 2.23694}

# Call codes seen in common feeds. These are defaults for convenience, not verified against any vendor;
# anything not listed raises, so nothing is guessed.
DEFAULT_CALLS = {
    "B": "ball", "C": "called_strike", "S": "swinging_strike", "W": "swinging_strike_blocked", "F": "foul",
    "T": "foul_tip", "L": "foul_bunt", "M": "missed_bunt", "X": "hit_into_play", "D": "hit_into_play",
    "E": "hit_into_play", "H": "hit_by_pitch", "*B": "blocked_ball",
    "Ball": "ball", "BallCalled": "ball", "StrikeCalled": "called_strike", "StrikeSwinging": "swinging_strike",
    "FoulBall": "foul", "FoulTip": "foul_tip", "InPlay": "hit_into_play", "HitByPitch": "hit_by_pitch",
    "ball": "ball", "called_strike": "called_strike", "swinging_strike": "swinging_strike", "foul": "foul",
    "foul_tip": "foul_tip", "hit_into_play": "hit_into_play", "hit_by_pitch": "hit_by_pitch",
}
REFERENCE_PATH = pathlib.Path(__file__).with_name("field_reference_mlb_2025.json")
REFERENCE_FIELDS = ["release_speed", "plate_x", "plate_z", "pfx_z", "api_break_x_batter_in", "sz_top", "sz_bot",
                    "launch_speed", "launch_angle", "bat_speed", "swing_length", "attack_angle"]


@dataclass
class ColumnMap:
    columns: dict                                        # canonical name -> your column name
    units: dict = field(default_factory=dict)            # canonical -> ft|in|cm|m for lengths, mph|kph|mps for speeds
    values: dict = field(default_factory=dict)           # canonical -> {your value: canonical value}
    hb_convention: str = "batter_relative"               # or "catcher_view" (+ toward first base side)
    plate_x_sign: float = 1.0                            # -1 if your + is toward third base
    system: str = "unknown"

    @classmethod
    def from_json(cls, text: str) -> "ColumnMap":
        return cls(**json.loads(text))

    def check(self) -> None:
        missing = [c for c in REQUIRED if c not in self.columns]
        if missing:
            raise ValueError(f"column map lacks required fields: {missing}")
        if self.hb_convention not in ("batter_relative", "catcher_view"):
            raise ValueError("hb_convention must be batter_relative or catcher_view")
        bad = [c for c in self.columns if c not in REQUIRED + OPTIONAL]
        if bad:
            raise ValueError(f"unknown canonical fields in column map: {bad}")


def infer_profile(cmap: ColumnMap, park: str = "") -> DataProfile:
    c = cmap.columns
    shape = "ivb" in c and "hb" in c and ("approach_angle" in c or all(k in c for k in ("vy0", "vz0", "ay", "az")))
    return DataProfile(
        park=park, system=cmap.system, has_location="plate_x" in c and "plate_z" in c, has_velo="velo" in c,
        has_pitch_shape=shape, has_batted_ball="launch_speed" in c and "launch_angle" in c,
        has_bat_tracking="bat_speed" in c, has_pitcher_state=all(k in c for k in ("at_bat", "pitch_no", "inning")))


def _num(v: Optional[str]) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "NA", "null") else None
    except ValueError:
        return None


def _fmt(v: Optional[float]) -> str:
    return "" if v is None else repr(round(v, 6))


def convert(text: str, cmap: ColumnMap, profile: Optional[DataProfile] = None, xwoba_model: Optional[EvLaXwoba] = None,
            strict: bool = True) -> tuple[str, dict]:
    """Returns (Savant-style CSV text, report). Report has counts, unmapped values, dropped rows and
    the sanity warnings from sanity_check."""
    cmap.check()
    off = (profile.offsets if profile else {}) or {}
    calls = {**DEFAULT_CALLS, **cmap.values.get("call", {})}
    src = list(csv.DictReader(io.StringIO(text)))
    if not src:
        raise ValueError("export is empty")
    lack = [v for v in cmap.columns.values() if v not in src[0]]
    if lack:
        raise ValueError(f"export lacks mapped columns: {lack}")

    def get(row, name):
        col = cmap.columns.get(name)
        return row[col] if col else None

    def length(row, name, extra_off=0.0):
        v = _num(get(row, name))
        return None if v is None else v * LENGTH_TO_FT[cmap.units.get(name, "ft")] + extra_off

    unmapped: Counter = Counter()
    dropped = 0
    out = []
    for row in src:
        call = calls.get(get(row, "call"))
        if call is None:
            unmapped[get(row, "call")] += 1
            continue
        stand = cmap.values.get("stand", {}).get(get(row, "stand"), get(row, "stand"))
        p_throws = cmap.values.get("p_throws", {}).get(get(row, "p_throws"), get(row, "p_throws"))
        if stand not in ("R", "L") or p_throws not in ("R", "L"):
            dropped += 1
            continue
        px = length(row, "plate_x", off.get("plate_x_ft", 0.0))
        pz = length(row, "plate_z", off.get("plate_z_ft", 0.0))
        velo = _num(get(row, "velo"))
        if px is None or pz is None or velo is None:
            dropped += 1
            continue
        velo = velo * SPEED_TO_MPH[cmap.units.get("velo", "mph")] + off.get("velo_mph", 0.0)
        rec = {
            "game_pk": get(row, "game_id"), "game_date": get(row, "date"), "batter": get(row, "batter_id"),
            "pitcher": get(row, "pitcher_id"), "stand": stand, "p_throws": p_throws, "balls": get(row, "balls"),
            "strikes": get(row, "strikes"), "at_bat_number": get(row, "at_bat"), "pitch_number": get(row, "pitch_no"),
            "inning": get(row, "inning"), "pitch_type": cmap.values.get("pitch_type", {}).get(get(row, "pitch_type"), get(row, "pitch_type")),
            "release_speed": _fmt(velo), "plate_x": _fmt(px * cmap.plate_x_sign), "plate_z": _fmt(pz), "description": call,
            "sz_top": _fmt(length(row, "sz_top")), "sz_bot": _fmt(length(row, "sz_bot")),
            "events": get(row, "event") or "", "outs_when_up": get(row, "outs") or "",
            "on_1b": get(row, "on_1b") or "", "on_2b": get(row, "on_2b") or "", "on_3b": get(row, "on_3b") or "",
            "bat_score": get(row, "bat_score") or "", "fld_score": get(row, "fld_score") or "",
            "inning_topbot": get(row, "inning_topbot") or "",
            "launch_speed": _fmt(_num(get(row, "launch_speed"))), "launch_angle": _fmt(_num(get(row, "launch_angle"))),
            "bat_speed": _fmt(_num(get(row, "bat_speed"))), "swing_length": _fmt(_num(get(row, "swing_length"))),
            "attack_angle": _fmt(_num(get(row, "attack_angle"))), "approach_angle": _fmt(_num(get(row, "approach_angle"))),
        }
        for k in ("vy0", "vz0", "ay", "az"):
            rec[k] = _fmt(_num(get(row, k)))
        ivb = _num(get(row, "ivb"))
        hb = _num(get(row, "hb"))
        if ivb is not None:
            rec["pfx_z"] = _fmt((ivb * LENGTH_TO_FT[cmap.units.get("ivb", "in")] * 12.0 + off.get("ivb_in", 0.0)) / 12.0) if cmap.units.get("ivb", "in") in ("in", "ft", "cm", "m") else ""
        if hb is not None:
            hb_ft = hb * LENGTH_TO_FT[cmap.units.get("hb", "in")] + off.get("hb_in", 0.0) / 12.0
            if cmap.hb_convention == "catcher_view":
                rec["pfx_x"] = _fmt(hb_ft)
                rec["api_break_x_batter_in"] = _fmt(-hb_ft if stand == "R" else hb_ft)   # Savant: R: -pfx_x, L: +pfx_x (measured)
            else:
                rec["api_break_x_batter_in"] = _fmt(hb_ft)
                rec["pfx_x"] = _fmt(-hb_ft if stand == "R" else hb_ft)
        ew = _num(get(row, "expected_woba"))
        rec["estimated_woba_source"] = ""
        if call == "hit_into_play":
            if ew is not None:
                rec["estimated_woba_using_speedangle"] = _fmt(ew)
                rec["estimated_woba_source"] = "export"
            elif xwoba_model is not None and rec["launch_speed"] and rec["launch_angle"]:
                rec["estimated_woba_using_speedangle"] = _fmt(float(xwoba_model(float(rec["launch_speed"]), float(rec["launch_angle"]))))
                rec["estimated_woba_source"] = "evla"
        out.append(rec)
    if unmapped and strict:
        raise ValueError(f"unmapped call values (add to values.call): {dict(unmapped)}")
    derive_state(out)
    header = KEEP + [c for c in EXTRA_COLUMNS if c not in KEEP]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore")
    w.writeheader()
    w.writerows(out)
    report = {"rows_in": len(src), "rows_out": len(out), "dropped_bad_hand_or_position": dropped,
              "unmapped_calls": dict(unmapped), "warnings": sanity_check(out)}
    return buf.getvalue(), report


def derive_state(rows: list[dict]) -> None:
    """Times through the order and prior plate appearances vs this pitcher today, from the pitch sequence."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["game_pk"], r["pitcher"])].append(r)
    for grp in groups.values():
        grp.sort(key=lambda r: (int(float(r["at_bat_number"])), int(float(r["pitch_number"]))))
        seen: dict[str, int] = defaultdict(int)
        last_ab = None
        for r in grp:
            ab = r["at_bat_number"]
            if ab != last_ab:
                last_ab = ab
                prior = seen[r["batter"]]
                seen[r["batter"]] += 1
            r["n_priorpa_thisgame_player_at_bat"] = prior
            r["n_thruorder_pitcher"] = prior + 1


# ------------------------------------------------------------------ sanity checks against MLB

def fit_reference(texts) -> dict:
    """Mean and SD of the checked fields over MLB pitch data, in Savant units."""
    acc = {f: [0, 0.0, 0.0] for f in REFERENCE_FIELDS}
    for t in texts:
        for r in csv.DictReader(io.StringIO(t)):
            for f in REFERENCE_FIELDS:
                v = _num(r.get(f))
                if v is not None:
                    a = acc[f]
                    a[0] += 1
                    a[1] += v
                    a[2] += v * v
    ref = {}
    for f, (n, s, ss) in acc.items():
        if n > 100:
            m = s / n
            ref[f] = {"mean": m, "sd": math.sqrt(max(ss / n - m * m, 0.0)), "n": n}
    return ref


def sanity_check(rows: list[dict], ref: Optional[dict] = None, sd_ratio=(0.5, 2.0), mean_sd_shift: float = 3.0) -> list[str]:
    """Warn when a converted field's spread or level is implausible for baseball, which usually means a
    unit or sign error (horizontal break in feet vs inches shows up as an SD ratio near 12)."""
    if ref is None:
        ref = json.loads(REFERENCE_PATH.read_text()) if REFERENCE_PATH.exists() else {}
    warns = []
    for f, r in ref.items():
        vals = [v for v in (_num(row.get(f)) for row in rows) if v is not None]
        if len(vals) < 50:
            continue
        m = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))
        if r["sd"] > 0 and not (sd_ratio[0] <= sd / r["sd"] <= sd_ratio[1]):
            warns.append(f"{f}: SD {sd:.3g} vs MLB {r['sd']:.3g} (ratio {sd / r['sd']:.2f}); check the unit")
        if abs(m - r["mean"]) > mean_sd_shift * r["sd"]:
            warns.append(f"{f}: mean {m:.3g} vs MLB {r['mean']:.3g}; check units, sign or offset")
    return warns


# ------------------------------------------------------------------ system offsets

def estimate_offsets(a_rows: list[dict], b_rows: list[dict], fields: list[str],
                     key=lambda r: (r["game_pk"], r["at_bat_number"], r["pitch_number"])) -> dict:
    """Mean difference B - A for the same pitches measured by two systems, with standard error and n.
    Rows are converted (Savant-unit) records. Use the result as a DataProfile offset (add to system A's
    values to put them on B's scale)."""
    b_by = {key(r): r for r in b_rows}
    out = {}
    for f in fields:
        d = []
        for r in a_rows:
            o = b_by.get(key(r))
            va, vb = _num(r.get(f)), _num(o.get(f)) if o else None
            if va is not None and vb is not None:
                d.append(vb - va)
        if len(d) >= 30:
            m = sum(d) / len(d)
            sd = math.sqrt(sum((x - m) ** 2 for x in d) / (len(d) - 1))
            out[f] = {"offset": m, "se": sd / math.sqrt(len(d)), "n": len(d)}
    return out


def main(argv=None) -> int:
    """python -m gameplan.milb --export export.csv --map columnmap.json --out converted.csv [--park Visalia]"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True)
    ap.add_argument("--map", required=True, help="ColumnMap JSON (see examples/milb_columnmap_example.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--park", default="")
    ap.add_argument("--no-xwoba-fill", action="store_true", help="do not fill xwOBA from exit velocity and launch angle")
    ap.add_argument("--lenient", action="store_true", help="count unmapped calls and drop those rows instead of stopping")
    a = ap.parse_args(argv)
    cmap = ColumnMap.from_json(open(a.map).read())
    prof = infer_profile(cmap, a.park)
    xw = None if a.no_xwoba_fill else (EvLaXwoba.load() if prof.has_batted_ball else None)
    text, rep = convert(open(a.export, encoding="utf-8-sig").read(), cmap, prof, xw, strict=not a.lenient)
    pathlib.Path(a.out).write_text(text)
    print(f"tier {prof.tier().value}; model settings {prof.model_settings()}")
    print(f"rows in {rep['rows_in']}, out {rep['rows_out']}, dropped {rep['dropped_bad_hand_or_position']}, unmapped calls {rep['unmapped_calls']}")
    for w in rep["warnings"]:
        print("WARNING:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
