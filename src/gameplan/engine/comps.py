"""Find MLB pitchers who look like an opposing starter we cannot get video of.

The target is described by what an arsenal export gives us: throwing hand, release height and side, extension, arm angle, and for each pitch type its usage, velocity and movement.
The pool is every 2025 MLB pitcher with enough pitches (built from the league pitch files by `build_pool`). The ranking is a plain distance, shown piece by piece so a person can overrule it:

  * same throwing hand is required (a left-hander is never offered as a comp for a right-hander unless the caller asks);
  * arm block: release height, release side, extension and arm angle, each scaled by how much MLB pitchers differ on it;
  * arsenal block: for each pitch the target throws (weighted by usage) the nearest-sized gap in velocity, horizontal and induced vertical break to the same pitch type of the comp;
    a pitch the comp does not throw costs MISS, and a pitch the comp leans on that the target does not throw costs its usage.

This is a similarity screen, not a claim that hitters read the two pitchers the same way. The admin picks, and the pack says plainly that it is a comp.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import pathlib
import statistics

POOL_FILE = pathlib.Path(__file__).with_name("comps_pool_2025.json")
MIN_PITCHES = 500            # to be in the pool
MIN_TYPE_N = 40              # pitches of one type before it counts as part of his arsenal
MIN_USAGE = 0.05
MISS = 3.0                   # cost, in pooled standard deviations, of a pitch the comp does not throw
EXTRA_WEIGHT = 1.5
W_ARM, W_ARS = 1.0, 1.0
ARM_FEATURES = ("rel_z", "rel_x", "ext", "arm_angle")

TYPE_ALIASES = {
    "FF": "FF", "FOURSEAM": "FF", "FOURSEAMFASTBALL": "FF", "FASTBALL": "FF", "4-SEAM FASTBALL": "FF", "FOUR-SEAM": "FF",
    "SI": "SI", "SINKER": "SI", "TWOSEAM": "SI", "TWOSEAMFASTBALL": "SI", "2-SEAM FASTBALL": "SI", "FT": "SI",
    "FC": "FC", "CUTTER": "FC", "SL": "SL", "SLIDER": "SL", "ST": "ST", "SWEEPER": "ST", "SV": "SV", "SLURVE": "SV",
    "CU": "CU", "CURVEBALL": "CU", "CURVE": "CU", "KC": "CU", "CS": "CU", "CH": "CH", "CHANGEUP": "CH", "CHANGE-UP": "CH", "FS": "FS", "SPLITTER": "FS", "SPLIT-FINGER": "FS", "FO": "FS", "KN": "KN", "KNUCKLEBALL": "KN",
}
COLS = dict(
    hand=("p_throws", "PitcherThrows", "Throws"), type=("pitch_type", "TaggedPitchType", "AutoPitchType", "PitchType"), speed=("release_speed", "RelSpeed"),
    rel_z=("release_pos_z", "RelHeight"), rel_x=("release_pos_x", "RelSide"), ext=("release_extension", "Extension"), arm=("arm_angle", "ArmAngle"),
    hb_ft=("pfx_x",), ivb_ft=("pfx_z",), hb_in=("HorzBreak",), ivb_in=("InducedVertBreak",), name=("player_name", "Pitcher"), id=("pitcher", "PitcherId"),
)


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _col(row: dict, key: str):
    for k in COLS[key]:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def norm_hand(v):
    s = str(v or "").strip().upper()
    return "R" if s.startswith("R") else "L" if s.startswith("L") else None


def norm_type(v):
    return TYPE_ALIASES.get(str(v or "").strip().upper().replace("_", ""))


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def summarize(rows) -> dict | None:
    """One pitcher's pitch rows (Statcast or TrackMan style columns) -> his profile. None when there is nothing usable."""
    acc, hands, names, arm = {}, [], [], dict(rel_z=[], rel_x=[], ext=[], arm_angle=[])
    n = 0
    for r in rows:
        t = norm_type(_col(r, "type"))
        v = _f(_col(r, "speed"))
        if t is None or v is None:
            continue
        n += 1
        hands.append(norm_hand(_col(r, "hand")))
        names.append(_col(r, "name"))
        arm["rel_z"].append(_f(_col(r, "rel_z")))
        rx = _f(_col(r, "rel_x"))
        arm["rel_x"].append(abs(rx) if rx is not None else None)            # a release is on the pitcher's own side; the sign convention differs between sources
        arm["ext"].append(_f(_col(r, "ext")))
        arm["arm_angle"].append(_f(_col(r, "arm")))
        hb = _f(_col(r, "hb_in"))
        hb = hb if hb is not None else (_f(_col(r, "hb_ft")) * 12 if _f(_col(r, "hb_ft")) is not None else None)
        ivb = _f(_col(r, "ivb_in"))
        ivb = ivb if ivb is not None else (_f(_col(r, "ivb_ft")) * 12 if _f(_col(r, "ivb_ft")) is not None else None)
        a = acc.setdefault(t, dict(v=[], hb=[], ivb=[]))
        a["v"].append(v)
        a["hb"].append(abs(hb) if hb is not None else None)                  # compared within a pitch type, where the break always goes the same way
        a["ivb"].append(ivb)
    hs = [h for h in hands if h]
    if n == 0 or not hs:
        return None
    pitches = {}
    for t, a in acc.items():
        if len(a["v"]) >= MIN_TYPE_N and len(a["v"]) / n >= MIN_USAGE:
            pitches[t] = dict(usage=round(len(a["v"]) / n, 4), velo=_mean(a["v"]), hb=_mean(a["hb"]), ivb=_mean(a["ivb"]), n=len(a["v"]))
    if not pitches:
        return None
    ns = next((x for x in names if x), None)
    return dict(name=ns, hand=max(set(hs), key=hs.count), n=n, rel_z=_med(arm["rel_z"]), rel_x=_med(arm["rel_x"]), ext=_med(arm["ext"]), arm_angle=_med(arm["arm_angle"]), pitches=pitches)


def profile_from_rows(rows: list) -> dict:
    """A staff upload (an arsenal export) -> profile, or raises ValueError saying what is missing."""
    p = summarize(rows)
    if p is None:
        raise ValueError("No usable pitches found. The file needs a pitch type, a speed and the throwing hand on each row.")
    miss = [k for k in ("rel_z", "rel_x", "ext") if p[k] is None]
    p["warnings"] = [f"No {k.replace('_', ' ')} in the file: it is left out of the comparison." for k in miss] + (["No arm angle in the file: it is left out of the comparison."] if p["arm_angle"] is None else [])
    return p


def profile_from_form(f: dict) -> dict:
    """Typed in by hand: hand, release height, side, extension, arm angle (optional) and up to six pitches 'TYPE usage velo hb ivb'."""
    hand = norm_hand(f.get("hand"))
    if hand is None:
        raise ValueError("Pick the throwing hand.")
    p = dict(name=(f.get("name") or "").strip() or None, hand=hand, n=0, rel_z=_f(f.get("rel_z")), rel_x=abs(_f(f.get("rel_x"))) if _f(f.get("rel_x")) is not None else None, ext=_f(f.get("ext")),
             arm_angle=_f(f.get("arm_angle")), pitches={}, warnings=[])
    for i in range(1, 7):
        t = norm_type(f.get(f"t{i}"))
        if t is None:
            continue
        u, v, hb, ivb = (_f(f.get(f"{k}{i}")) for k in ("u", "v", "h", "i"))
        if u is None or v is None:
            raise ValueError(f"Pitch {i}: usage and velocity are needed.")
        p["pitches"][t] = dict(usage=u / 100 if u > 1 else u, velo=v, hb=abs(hb) if hb is not None else None, ivb=ivb, n=0)
    if not p["pitches"]:
        raise ValueError("Add at least one pitch.")
    p["warnings"] = [f"No {k.replace('_', ' ')}: it is left out of the comparison." for k in ("rel_z", "rel_x", "ext", "arm_angle") if p[k] is None]
    return p


# ---------------------------------------------------------------------------- the pool
def fetch_names(ids: list, fetch=None) -> dict:
    """{mlbam id: full name} from the MLB Stats API. The league pitch files carry the BATTER's name in player_name, so the pitcher's name must come from here."""
    import urllib.request

    def get(url):
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
    fetch = fetch or get
    out = {}
    for i in range(0, len(ids), 150):
        d = fetch("https://statsapi.mlb.com/api/v1/people?personIds=" + ",".join(str(x) for x in ids[i:i + 150]))
        out.update({p["id"]: p["fullName"] for p in d.get("people", [])})
    return out


def build_pool(src_glob: str, season: int, out: pathlib.Path | None = None, names: dict | None = None) -> dict:
    by = {}
    firsts = {}
    for f in sorted(glob.glob(src_glob)):
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                pid = r.get("pitcher")
                if not pid:
                    continue
                by.setdefault(pid, []).append(r)
                if r.get("inning") == "1":
                    firsts.setdefault(pid, set()).add(r.get("game_pk"))
    pitchers = []
    for pid, rows in by.items():
        if len(rows) < MIN_PITCHES:
            continue
        p = summarize(rows)
        if p is None:
            continue
        p["id"] = int(pid)
        p["name"] = (names or {}).get(int(pid)) or f"Pitcher {pid}"
        p["starts"] = len(firsts.get(pid, ()))
        pitchers.append(p)
    pitchers.sort(key=lambda p: p["id"])
    pool = dict(season=season, source=str(src_glob), pitchers=pitchers, scale=_scale(pitchers))
    if out:
        pathlib.Path(out).write_text(json.dumps(pool, separators=(",", ":")))
    return pool


def _sd(xs):
    xs = [x for x in xs if x is not None]
    return statistics.pstdev(xs) if len(xs) > 2 else 1.0


def _scale(pitchers) -> dict:
    sc = dict(arm={k: max(_sd([p[k] for p in pitchers]), 1e-6) for k in ARM_FEATURES}, pitch={})
    for t in {t for p in pitchers for t in p["pitches"]}:
        rows = [p["pitches"][t] for p in pitchers if t in p["pitches"]]
        sc["pitch"][t] = {k: max(_sd([r[k] for r in rows]), 1e-6) for k in ("velo", "hb", "ivb")}
    return sc


_cache: dict = {}


def load_pool(path: pathlib.Path | None = None) -> dict:
    path = pathlib.Path(path or POOL_FILE)
    key = (str(path), path.stat().st_mtime if path.exists() else 0)
    if key not in _cache:
        _cache.clear()
        _cache[key] = json.loads(path.read_text())
    return _cache[key]


# ---------------------------------------------------------------------------- the ranking
def distance(target: dict, comp: dict, scale: dict) -> dict:
    parts = []
    arm_terms = {}
    for k in ARM_FEATURES:
        a, b = target.get(k), comp.get(k)
        if a is None or b is None:
            continue
        arm_terms[k] = (a - b) / scale["arm"][k]
    arm = math.sqrt(sum(v * v for v in arm_terms.values()) / len(arm_terms)) if arm_terms else 0.0
    tot_u = sum(p["usage"] for p in target["pitches"].values()) or 1.0
    ars, rows = 0.0, []
    for t, tp in target["pitches"].items():
        w = tp["usage"] / tot_u
        cp = comp["pitches"].get(t)
        if cp is None:
            ars += w * MISS
            rows.append(dict(type=t, usage=tp["usage"], missing=True))
            continue
        d, diffs = [], {}
        for k in ("velo", "hb", "ivb"):
            if tp.get(k) is None or cp.get(k) is None:
                continue
            diffs[k] = round(cp[k] - tp[k], 2)
            d.append(((cp[k] - tp[k]) / scale["pitch"][t][k]) ** 2)
        c = math.sqrt(sum(d) / len(d)) if d else MISS
        ars += w * c
        rows.append(dict(type=t, usage=tp["usage"], comp_usage=cp["usage"], diffs=diffs, cost=round(c, 2)))
    extra = sum(cp["usage"] for t, cp in comp["pitches"].items() if t not in target["pitches"] and cp["usage"] >= 0.10)
    ars += EXTRA_WEIGHT * extra
    return dict(total=W_ARM * arm + W_ARS * ars, arm=arm, arsenal=ars, arm_diffs={k: round(comp[k] - target[k], 2) for k in arm_terms}, pitches=rows, extra_usage=round(extra, 3))


def rank(target: dict, pool: dict | None = None, n: int = 5, same_hand: bool = True, starters_only: bool = True, exclude_ids=()) -> list:
    pool = pool or load_pool()
    if not target.get("pitches"):
        raise ValueError("The target has no pitches.")
    out = []
    for comp in pool["pitchers"]:
        if comp["id"] in exclude_ids or (same_hand and comp["hand"] != target["hand"]) or (starters_only and comp.get("starts", 0) < 5):
            continue
        d = distance(target, comp, pool["scale"])
        out.append(dict(id=comp["id"], name=comp["name"], hand=comp["hand"], n=comp["n"], starts=comp.get("starts"), **d))
    out.sort(key=lambda r: (r["total"], r["id"]))
    return out[:n]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the MLB comparison pool from league pitch files.")
    ap.add_argument("--src", required=True, help="glob of league csv files, e.g. 'data/league/2025-*.csv'")
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--out", default=str(POOL_FILE))
    a = ap.parse_args()
    ids = sorted({int(r["pitcher"]) for f in glob.glob(a.src) for r in csv.DictReader(open(f)) if r.get("pitcher")})
    pool = build_pool(a.src, a.season, pathlib.Path(a.out), fetch_names(ids))
    print(f"{len(pool['pitchers'])} pitchers -> {a.out}")
