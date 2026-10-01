"""Onboarding kit for a new tracking export (TrackMan, Hawk-Eye or other).

Give it a sample export (a few thousand pitches is enough). It proposes a column map, infers units and sign
conventions by comparing the data with 2025 MLB distributions, and says what it could not decide. With a second export
from a different system it estimates the offset between the systems from pitchers who threw in both.

Nothing is applied silently: the output is a proposed ColumnMap plus a report for a person to confirm. Header names below
are common names from public documentation and are suggestions only, not a claim about any vendor's current export.

    python -m gameplan.onboard --export sample.csv --out onboarding_report.md --write-map columnmap.json
    python -m gameplan.onboard --export trackman_sample.csv --export-b hawkeye_sample.csv --out report.md
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import pathlib
import re
from collections import defaultdict

import numpy as np

from .milb import LENGTH_TO_FT, REFERENCE_PATH, REQUIRED, SPEED_TO_MPH, ColumnMap, _num

SIGNS_PATH = pathlib.Path(__file__).with_name("field_reference_signs_2025.json")

# Normalized (lowercase letters and digits only) header names per canonical field. First match wins.
ALIASES = {
    "game_id": ["gamepk", "gameid", "gameuid", "game", "gamenumber"],
    "date": ["gamedate", "date", "gamedatetime"],
    "batter_id": ["batter", "batterid", "batterkey", "batteridmlb"],
    "pitcher_id": ["pitcher", "pitcherid", "pitcherkey", "pitcheridmlb"],
    "stand": ["stand", "batterside", "battershand", "batside", "batterhand"],
    "p_throws": ["pthrows", "pitcherthrows", "pitcherhand", "throws", "pitchhand"],
    "balls": ["balls", "ball", "ballcount"],
    "strikes": ["strikes", "strike", "strikecount"],
    "at_bat": ["atbatnumber", "paofinning", "atbat", "plateappearance", "paid", "pano"],
    "pitch_no": ["pitchnumber", "pitchofpa", "pitchno", "pitchinpa", "pitchnum"],
    "inning": ["inning", "inn"],
    "pitch_type": ["pitchtype", "taggedpitchtype", "autopitchtype", "pitchname"],
    "velo": ["releasespeed", "relspeed", "pitchspeed", "velocity", "startspeed", "velo"],
    "plate_x": ["platex", "platelocside", "platelocsidefeet", "pitchlocx", "px"],
    "plate_z": ["platez", "platelocheight", "platelocheightfeet", "pitchlocz", "pz"],
    "call": ["description", "pitchcall", "pitchresult", "call", "pitchoutcome"],
    "sz_top": ["sztop", "zonetop", "strikezonetop"],
    "sz_bot": ["szbot", "zonebottom", "strikezonebottom"],
    "ivb": ["inducedvertbreak", "pfxz", "ivb", "inducedverticalbreak", "verticalbreakinduced"],
    "hb": ["horzbreak", "apibreakxbatterin", "pfxx", "hb", "horizontalbreak"],
    "approach_angle": ["vertapprangle", "vaa", "verticalapproachangle", "approachangle"],
    "launch_speed": ["launchspeed", "exitspeed", "exitvelo", "exitvelocity", "ev"],
    "launch_angle": ["launchangle", "angle", "la"],
    "bat_speed": ["batspeed", "batspeedmph"],
    "swing_length": ["swinglength"],
    "attack_angle": ["attackangle"],
    "event": ["events", "playresult", "event", "kororbb"],
    "outs": ["outswhenup", "outs"],
    "inning_topbot": ["inningtopbot", "topbottom", "topbot"],
    "expected_woba": ["estimatedwobausingspeedangle", "xwoba"],
}

# canonical field -> (MLB reference field in field_reference_mlb_2025.json, candidate unit -> factor to the reference unit)
UNIT_CHECKS = {
    "velo": ("release_speed", SPEED_TO_MPH),
    "plate_x": ("plate_x", LENGTH_TO_FT),
    "plate_z": ("plate_z", LENGTH_TO_FT),
    "sz_top": ("sz_top", LENGTH_TO_FT),
    "sz_bot": ("sz_bot", LENGTH_TO_FT),
    "ivb": ("pfx_z", LENGTH_TO_FT),
    "hb": ("api_break_x_batter_in", LENGTH_TO_FT),
    "swing_length": ("swing_length", LENGTH_TO_FT),
}
FASTBALLS = {"ff", "si", "fastball", "fourseamfastball", "fourseam", "sinker", "twoseamfastball", "twoseam", "fastballfourseam"}
RHL = {"r": "R", "right": "R", "righty": "R", "rhp": "R", "rhh": "R", "l": "L", "left": "L", "lefty": "L", "lhp": "L", "lhh": "L"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def suggest_map(header: list[str]) -> dict:
    """Propose canonical -> your column. Returns columns, required fields still missing, and fields with several candidates."""
    by_norm: dict[str, list[str]] = defaultdict(list)
    for h in header:
        by_norm[_norm(h)].append(h)
    columns, ambiguous, used = {}, {}, set()
    for canon, names in ALIASES.items():
        hits = [(n, h) for n in names for h in by_norm.get(n, []) if h not in used]
        if hits:
            columns[canon] = hits[0][1]
            used.add(hits[0][1])
            if len({h for _, h in hits}) > 1:
                ambiguous[canon] = sorted({h for _, h in hits})
    return {"columns": columns, "missing_required": [c for c in REQUIRED if c not in columns], "ambiguous": ambiguous}


def detect_scale(values: np.ndarray, ref: dict, candidates: dict) -> dict:
    """Which candidate unit puts these values on the MLB reference scale. Margin below 0.35 means too close to call."""
    if len(values) < 50:
        return {"unit": None, "margin": 0.0, "note": "fewer than 50 values"}
    sd, mean = float(np.std(values)), float(np.mean(values))
    scores = {}
    for unit, k in candidates.items():
        scores[unit] = abs(math.log(max(sd * k, 1e-9) / ref["sd"])) + 0.25 * abs((mean * k - ref["mean"]) / ref["sd"]) ** 0.5
    ranked = sorted(scores, key=scores.get)
    margin = scores[ranked[1]] - scores[ranked[0]] if len(ranked) > 1 else 9.0
    return {"unit": ranked[0], "margin": round(margin, 2), "sd_ratio_after": round(sd * candidates[ranked[0]] / ref["sd"], 2)}


def infer_units(rows: list[dict], columns: dict) -> tuple[dict, list[str]]:
    ref = json.loads(REFERENCE_PATH.read_text())
    units, notes = {}, []
    for canon, (ref_field, cands) in UNIT_CHECKS.items():
        if canon not in columns or ref_field not in ref:
            continue
        v = np.array([x for x in (_num(r.get(columns[canon])) for r in rows) if x is not None])
        res = detect_scale(v, ref[ref_field], cands)
        if res["unit"] is None:
            notes.append(f"{canon}: {res['note']}")
            continue
        units[canon] = res["unit"]
        flag = "" if res["margin"] >= 0.35 else "  (too close to call: confirm by hand)"
        notes.append(f"{canon}: looks like {res['unit']} (SD ratio to MLB {res['sd_ratio_after']}, margin {res['margin']}){flag}")
    return units, notes


def _hand(v: str, value_map: dict | None = None):
    if value_map and v in value_map:
        return value_map[v]
    return RHL.get(_norm(v or ""))


def infer_conventions(rows: list[dict], columns: dict, units: dict) -> tuple[dict, list[str]]:
    """plate_x sign and horizontal-break convention from fastball and batter-side patterns, against 2025 MLB."""
    sig = json.loads(SIGNS_PATH.read_text())
    out, notes = {}, []
    if all(k in columns for k in ("plate_x", "stand")):
        by = defaultdict(list)
        for r in rows:
            h, x = _hand(r.get(columns["stand"])), _num(r.get(columns["plate_x"]))
            if h and x is not None:
                by[h].append(x)
        if len(by["R"]) >= 100 and len(by["L"]) >= 100:
            mlb = sig["px|R"]["mean"] - sig["px|L"]["mean"]
            mine = float(np.mean(by["R"]) - np.mean(by["L"])) * LENGTH_TO_FT.get(units.get("plate_x", "ft"), 1.0)
            out["plate_x_sign"] = 1.0 if mine * mlb > 0 else -1.0
            notes.append(f"plate_x: right-handed minus left-handed batters {mine:+.2f} ft vs MLB {mlb:+.2f}; sign {'matches' if mine * mlb > 0 else 'is flipped'}"
                         + ("  (weak: confirm by hand)" if abs(mine) < 0.08 else ""))
    need = ("hb", "p_throws", "stand", "pitch_type")
    if all(k in columns for k in need):
        cells = defaultdict(list)
        scale = LENGTH_TO_FT.get(units.get("hb", "in"), 1 / 12)
        for r in rows:
            if _norm(r.get(columns["pitch_type"], "")) not in FASTBALLS:
                continue
            p, b, v = _hand(r.get(columns["p_throws"])), _hand(r.get(columns["stand"])), _num(r.get(columns["hb"]))
            if p and b and v is not None:
                cells[(p, b)].append(v * scale)
        if all(len(cells[k]) >= 30 for k in (("R", "R"), ("R", "L"), ("L", "R"), ("L", "L"))):
            m = {k: float(np.mean(v)) for k, v in cells.items()}
            cat = {k: sig[f"pfx_x|{k[0]}|{k[1]}"]["mean"] for k in m}                 # MLB catcher-view signature
            bat = {k: sig[f"api_break_x_batter_in|{k[0]}|{k[1]}"]["mean"] for k in m}  # MLB batter-relative signature
            corr = lambda a, b: float(np.corrcoef([a[k] for k in sorted(a)], [b[k] for k in sorted(b)])[0, 1])
            c_cat, c_bat = corr(m, cat), corr(m, bat)
            conv = "catcher_view" if abs(c_cat) > abs(c_bat) else "batter_relative"
            ref_corr = c_cat if conv == "catcher_view" else c_bat
            out["hb_convention"], out["hb_sign"] = conv, 1.0 if ref_corr > 0 else -1.0
            notes.append(f"hb: fastball horizontal break by pitcher hand and batter side matches MLB {conv} "
                         f"(r = {ref_corr:+.2f}); {'same' if ref_corr > 0 else 'opposite'} sign"
                         + ("" if min(abs(c_cat), abs(c_bat)) < 0.5 * max(abs(c_cat), abs(c_bat)) else "  (the two patterns are close: confirm by hand)"))
        else:
            notes.append("hb: need 30+ fastballs in each pitcher-hand by batter-side cell to infer the convention")
    return out, notes


def compare_systems(rows_a: list[dict], rows_b: list[dict], fields: list[str], n_boot: int = 200, seed: int = 0) -> dict:
    """Mean difference B minus A on matched pitcher x pitch type groups (pitchers who threw in both systems' parks), with a
    pitcher-cluster bootstrap interval. Rows are converted (Savant-unit) records. Park, weather and altitude are confounded
    with the system, so treat the result as an upper bound on the pure system offset until paired pitches exist."""
    def groups(rows):
        g = defaultdict(lambda: defaultdict(list))
        for r in rows:
            for f in fields:
                v = _num(r.get(f))
                if v is not None:
                    g[(r["pitcher"], r["pitch_type"])][f].append(v)
        return g
    ga, gb = groups(rows_a), groups(rows_b)
    out = {}
    for f in fields:
        per = defaultdict(list)                                  # pitcher -> [(diff, weight)]
        for key in set(ga) & set(gb):
            a, b = ga[key].get(f, []), gb[key].get(f, [])
            if len(a) >= 10 and len(b) >= 10:
                per[key[0]].append((float(np.mean(b) - np.mean(a)), min(len(a), len(b))))
        if len(per) < 5:
            continue
        pitchers = list(per)
        stat = lambda idx: (sum(d * w for i in idx for d, w in per[pitchers[i]]) / sum(w for i in idx for _, w in per[pitchers[i]]))
        point = stat(range(len(pitchers)))
        rng = np.random.default_rng(seed)
        draws = [stat(rng.integers(0, len(pitchers), len(pitchers))) for _ in range(n_boot)]
        lo, hi = np.percentile(draws, [2.5, 97.5])
        out[f] = {"offset": point, "ci": [float(lo), float(hi)], "pitchers": len(pitchers)}
    return out


def build_map(rows: list[dict], header: list[str], system: str = "unknown") -> tuple[ColumnMap, list[str]]:
    sug = suggest_map(header)
    notes = []
    if sug["missing_required"]:
        notes.append(f"required fields with no matching column: {sug['missing_required']}")
    for k, v in sug["ambiguous"].items():
        notes.append(f"{k}: several candidate columns {v}; using {sug['columns'][k]}")
    units, unit_notes = infer_units(rows, sug["columns"])
    conv, conv_notes = infer_conventions(rows, sug["columns"], units)
    values = {}
    for k in ("stand", "p_throws"):
        if k in sug["columns"]:
            seen = {r.get(sug["columns"][k]) for r in rows}
            values[k] = {s: _hand(s) for s in seen if s and _hand(s)}
    cmap = ColumnMap(columns=sug["columns"], units=units, values=values, system=system,
                     hb_convention=conv.get("hb_convention", "batter_relative"), plate_x_sign=conv.get("plate_x_sign", 1.0),
                     hb_sign=conv.get("hb_sign", 1.0))
    notes += unit_notes + conv_notes
    notes.append("call values (balls, strikes, swings, contact) are NOT inferred: list them in values.call and re-run milb.convert")
    return cmap, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True)
    ap.add_argument("--export-b", default=None, help="a second system's export, to estimate the offset between systems")
    ap.add_argument("--system", default="unknown")
    ap.add_argument("--out", default="onboarding_report.md")
    ap.add_argument("--write-map", default=None)
    a = ap.parse_args(argv)
    text = open(a.export, encoding="utf-8-sig").read()
    rows = list(csv.DictReader(io.StringIO(text)))
    cmap, notes = build_map(rows, list(rows[0].keys()), a.system)
    lines = [f"# Onboarding report: {a.export}", f"{len(rows)} rows, {len(rows[0])} columns.", "", "## Proposed mapping", ""]
    lines += [f"- {k}: `{v}`" for k, v in cmap.columns.items()]
    lines += ["", "## Inferred and open items", ""] + [f"- {n}" for n in notes]
    lines += ["", "Confirm every line above before using the map. Then: `python -m gameplan.milb --export ... --map columnmap.json --out converted.csv`."]
    if a.export_b:
        from .milb import convert
        other = open(a.export_b, encoding="utf-8-sig").read()
        orows = list(csv.DictReader(io.StringIO(other)))
        cmap_b, notes_b = build_map(orows, list(orows[0].keys()), "system B")
        lines += ["", "## Second export", ""] + [f"- {n}" for n in notes_b]
        try:
            a_conv = list(csv.DictReader(io.StringIO(convert(text, cmap, strict=False)[0])))
            b_conv = list(csv.DictReader(io.StringIO(convert(other, cmap_b, strict=False)[0])))
            fields = ["release_speed", "plate_z", "pfx_z", "api_break_x_batter_in"]
            off = compare_systems(a_conv, b_conv, fields)
            lines += ["", "## Offset B minus A (matched pitchers; park effects included)", ""]
            lines += [f"- {f}: {v['offset']:+.3f} [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}] over {v['pitchers']} pitchers" for f, v in off.items()] or ["- not enough shared pitchers (need 5+ with 10+ pitches of a type in each system)"]
        except ValueError as e:
            lines += ["", f"Conversion needed before offsets can be estimated: {e}"]
    pathlib.Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if a.write_map:
        pathlib.Path(a.write_map).write_text(json.dumps(cmap.__dict__, indent=1))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
