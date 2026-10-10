"""Turn a pitch-level export (TruMedia, TrackMan or Statcast style) for one pitcher into pitches the app can draw, for starters who have no public tracking or video.

What a row must carry: pitch type, speed, plate location (side, height), the batter's side, the pitcher's hand, and either
  * the nine initial-condition numbers of the path (x0 y0 z0 vx0 vy0 vz0 ax ay az, Statcast axes), or
  * release height, release side, extension and the two breaks (horizontal, induced vertical). The path is then rebuilt: constant acceleration from the release point through the plate
    location, with the break fixing the sideways and vertical acceleration and drag modelled from speed.
Either way a row is drawn only if it passes the same checks as Savant tracking (simview.sim_params: reproduces the plate location, the speed, the flight time, moves toward the plate).
Rows that fail are counted with the reason, never drawn from partial numbers.

The direction of horizontal break differs between systems, so it is not assumed: arm-side pitches (fastball, sinker, changeup, splitter) run toward the pitcher's arm side and the glove-side group
(slider, sweeper, curve, cutter) the other way, and that fixes the sign. A file where the two groups cannot be told apart is refused.
Plate side is taken as positive toward the catcher's right (first base); `plate_sign=-1` flips it for a system that reports the other way.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import statistics

from .. import simview
from . import comps, db

G = 32.174
DRAG_K = 0.001613                   # ay = DRAG_K * speed^2 (ft/s); fitted on 15,600 Savant pitches, residual sd 2.5 ft/s^2
DEFAULT_ZONE = (3.4, 1.6)
MAX_BYTES = 5_000_000
MIN_ACCEPTED = 60

ALIAS = dict(
    type=("pitch_type", "taggedpitchtype", "autopitchtype", "pitchtype", "pitch"),
    speed=("release_speed", "relspeed", "start_speed", "velo", "velocity", "speed"),
    hand=("p_throws", "pitcherthrows", "throws", "pitcherhand"),
    stand=("stand", "batterside", "batside", "bats", "batterhand"),
    px=("plate_x", "platelocside", "platex", "px", "plateside"),
    pz=("plate_z", "platelocheight", "platez", "pz", "plateheight"),
    top=("sz_top", "sztop", "zonetop", "strikezonetop"),
    bot=("sz_bot", "szbot", "zonebottom", "strikezonebottom"),
    rel_z=("release_pos_z", "relheight", "releaseheight"),
    rel_x=("release_pos_x", "relside", "releaseside"),
    ext=("release_extension", "extension"),
    hb_ft=("pfx_x",), ivb_ft=("pfx_z",),
    hb_in=("horzbreak", "horizontalbreak", "hb", "horzbreakin"), ivb_in=("inducedvertbreak", "inducedverticalbreak", "ivb", "vertbreakinduced"),
    date=("game_date", "date", "gamedate"),
    name=("pitcher", "player_name", "pitchername"),
)
PHYS = dict(x0=("x0",), y0=("y0",), z0=("z0",), vx0=("vx0",), vy0=("vy0",), vz0=("vz0",), ax=("ax", "ax0"), ay=("ay", "ay0"), az=("az", "az0"))
ARM_SIDE = {"FF", "SI", "CH", "FS", "FO"}
GLOVE_SIDE = {"SL", "ST", "SV", "CU", "KC", "CS", "FC"}

_TYPES = {re.sub(r"[^A-Z0-9]", "", k.upper()): v for k, v in comps.TYPE_ALIASES.items()}
_TYPES.update({"KC": "KC", "KNUCKLECURVE": "KC", "CS": "CS", "SLOWCURVE": "CS", "EP": "EP", "EEPHUS": "EP"})


def norm_type(v):
    return _TYPES.get(re.sub(r"[^A-Z0-9]", "", str(v or "").upper()))


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", s.lower().strip().replace(" ", ""))


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _hand(v):
    s = str(v or "").strip().upper()
    return s[0] if s[:1] in ("L", "R") else None


def reconstruct(x_r, z_r, ext, speed_mph, px, pz, hb_ft, ivb_ft):
    """-> the nine path numbers at y=50 (Statcast axes), or None when no physical path fits. hb_ft is signed like Statcast pfx_x."""
    s = speed_mph / MPH_PER_FPS
    y_r = 60.5 - ext
    yp = simview.Y_PLATE
    ay = DRAG_K * s * s

    def solve(t):
        vx = (px - x_r - hb_ft) / t
        vz = (pz - z_r + 0.5 * G * t * t - ivb_ft) / t
        rest = s * s - vx * vx - vz * vz
        if rest <= 0:
            return None
        vy = -math.sqrt(rest)
        return vx, vy, vz, y_r + vy * t + 0.5 * ay * t * t - yp

    lo, hi = 0.28, 0.70
    flo, fhi = solve(lo), solve(hi)
    if flo is None or fhi is None or flo[3] * fhi[3] > 0:
        return None
    f_lo = flo[3]
    for _ in range(60):
        mid = (lo + hi) / 2
        fm = solve(mid)
        if fm is None:
            return None
        if fm[3] * f_lo <= 0:
            hi = mid
        else:
            lo, f_lo = mid, fm[3]
    t = (lo + hi) / 2
    vx, vy, vz, _ = solve(t)
    a = (2 * hb_ft / (t * t), ay, -G + 2 * ivb_ft / (t * t))
    c = 0.5 * ay
    b = vy
    d = y_r - 50.0
    disc = b * b - 4 * c * d
    if disc < 0:
        return None
    t1 = (-b - math.sqrt(disc)) / (2 * c)
    t1 = t1 if t1 >= 0 else (-b + math.sqrt(disc)) / (2 * c)
    pos = (x_r + vx * t1 + 0.5 * a[0] * t1 * t1, 50.0, z_r + vz * t1 + 0.5 * a[2] * t1 * t1)
    vel = (vx + a[0] * t1, vy + a[1] * t1, vz + a[2] * t1)
    return dict(x0=pos[0], y0=50.0, z0=pos[2], vx0=vel[0], vy0=vel[1], vz0=vel[2], ax=a[0], ay=a[1], az=a[2])


MPH_PER_FPS = simview.MPH


class Parsed(dict):
    """rows (feed-shaped), rejected {reason: count}, warnings, summary, ok, error"""


def parse(text: str, plate_sign: int = 1) -> Parsed:
    out = Parsed(rows=[], rejected={}, warnings=[], summary={}, ok=False, error=None, dates=[])
    if len(text.encode("utf-8", "ignore")) > MAX_BYTES:
        out["error"] = "That file is larger than 5 MB. Export fewer starts."
        return out
    try:
        rdr = csv.DictReader(io.StringIO(text.strip()))
        raw = list(rdr)
    except csv.Error as e:
        out["error"] = f"The file could not be read as a CSV: {e}"
        return out
    if not raw or not rdr.fieldnames:
        out["error"] = "The file has no rows. It needs a header row and one row per pitch."
        return out
    cols = {_key(h): h for h in rdr.fieldnames if h}

    def pick(names):
        return next((cols[n] for n in names if n in cols), None)

    cmap = {k: pick(v) for k, v in ALIAS.items()}
    pmap = {k: pick(v) for k, v in PHYS.items()}
    need = [k for k in ("type", "speed", "hand", "stand", "px", "pz") if cmap[k] is None]
    if need:
        names = dict(type="pitch type", speed="release speed", hand="pitcher's throwing hand", stand="batter's side", px="plate side", pz="plate height")
        out["error"] = "The file is missing: " + ", ".join(names[k] for k in need) + ". Columns found: " + ", ".join(list(rdr.fieldnames)[:25])
        return out
    full = all(pmap[k] for k in PHYS)
    brk = (cmap["hb_ft"] and cmap["ivb_ft"]) or (cmap["hb_in"] and cmap["ivb_in"])
    release = cmap["rel_z"] and cmap["rel_x"] and cmap["ext"]
    if not full and not (brk and release):
        out["error"] = ("To draw a pitch the file needs either the nine path numbers (x0 y0 z0 vx0 vy0 vz0 ax ay az) or release height, release side, extension, horizontal break and induced vertical break. "
                        "Columns found: " + ", ".join(list(rdr.fieldnames)[:25]))
        return out
    names = {r[cmap["name"]] for r in raw if cmap["name"] and r.get(cmap["name"])}
    if len(names) > 1:
        out["error"] = f"The file has {len(names)} different pitchers ({', '.join(sorted(names)[:4])}...). Export one pitcher at a time."
        return out
    hb_unit = 12.0 if cmap["hb_ft"] else None            # feet when named pfx_x, inches otherwise

    def rej(why):
        out["rejected"][why] = out["rejected"].get(why, 0) + 1

    # pass 1: values
    pre = []
    for r in raw:
        t = norm_type(r.get(cmap["type"]))
        h, st = _hand(r.get(cmap["hand"])), _hand(r.get(cmap["stand"]))
        sp, px, pz = (_num(r.get(cmap[k])) for k in ("speed", "px", "pz"))
        if t is None:
            rej("unknown pitch type")
        elif h is None or st is None:
            rej("hand or batter side not L or R")
        elif None in (sp, px, pz) or not 45 <= sp <= 110 or abs(px) > 4 or not -1 < pz < 7:
            rej("speed or plate location missing or out of range")
        else:
            pre.append(dict(r=r, t=t, h=h, st=st, sp=sp, px=px * plate_sign, pz=pz))
    hands = {p["h"] for p in pre}
    if len(hands) > 1:
        out["error"] = "The file mixes left- and right-handed throws. Export one pitcher at a time."
        return out
    hand = hands.pop() if hands else None
    if hand is None:
        out["error"] = "No usable rows. " + "; ".join(f"{n} {w}" for w, n in out["rejected"].items())
        return out

    # break direction, from the pitcher's own arsenal
    c_sign = 1.0
    if not full and cmap["hb_in"] and not cmap["hb_ft"]:
        every = [v for p in pre if (v := _num(p["r"].get(cmap["hb_in"]))) is not None]
        a_vals = [v for p in pre if p["t"] in ARM_SIDE and (v := _num(p["r"].get(cmap["hb_in"]))) is not None]
        g_vals = [v for p in pre if p["t"] in GLOVE_SIDE and (v := _num(p["r"].get(cmap["hb_in"]))) is not None]
        ma = statistics.median(a_vals) if len(a_vals) >= 10 else None
        mg = statistics.median(g_vals) if len(g_vals) >= 10 else None
        why = None
        if not every or not (min(every) < -2 and max(every) > 2):
            why = "the horizontal break values all point one way, so the file may report size without direction"
        elif ma is not None and mg is not None:
            if abs(ma - mg) < 3:
                why = f"his arm-side pitches average {ma:+.1f} in and his glove-side pitches {mg:+.1f} in, which are too close to tell apart"
            else:
                sig = 1 if ma > mg else -1
        elif ma is not None and abs(ma) >= 2:
            sig = 1 if ma > 0 else -1
        elif mg is not None and abs(mg) >= 2:
            sig = -1 if mg > 0 else 1
        else:
            why = "there are too few fastballs, sinkers, changeups or sliders with real movement"
        if why:
            out["error"] = f"Cannot tell which way horizontal break points: {why}. Send a sample file so the direction can be set by hand."
            return out
        expected = -1 if hand == "R" else 1                # Statcast: a right-hander's arm-side pitches run toward third base (negative x)
        c_sign = expected / sig
        out["summary"]["hb_direction"] = "flipped" if c_sign < 0 else "as exported"
    elif not full and cmap["hb_ft"]:
        a_vals = [v for p in pre if p["t"] in ARM_SIDE and (v := _num(p["r"].get(cmap["hb_ft"]))) is not None]
        if len(a_vals) >= 10 and abs(statistics.median(a_vals)) > 0.08 and (statistics.median(a_vals) > 0) != (hand == "L"):
            out["error"] = "Horizontal break (pfx_x) points the wrong way for this pitcher's arm-side pitches. The file may be mirrored; send a sample."
            return out

    zone_given = bool(cmap["top"] and cmap["bot"])
    if not zone_given:
        out["warnings"].append(f"The file has no strike-zone top and bottom, so {DEFAULT_ZONE[0]} and {DEFAULT_ZONE[1]} ft are used for every batter. Pocket labels and the strike/ball answer near the top and bottom edges are approximate.")
    rel = []
    n_dates = {}
    for i, p in enumerate(pre):
        r = p["r"]
        feed = dict(type="pitch", pitch_type=p["t"], stand=p["st"], p_throws=p["h"], start_speed=round(p["sp"], 1), px=round(p["px"], 3), pz=round(p["pz"], 3))
        top, bot = (_num(r.get(cmap["top"])), _num(r.get(cmap["bot"]))) if zone_given else (None, None)
        if top is None or bot is None or top <= bot:
            top, bot = DEFAULT_ZONE
        feed.update(sz_top=round(top, 3), sz_bot=round(bot, 3))
        if full:
            phys = {k: _num(r.get(pmap[k])) for k in PHYS}
            if None in phys.values():
                rej("path numbers missing")
                continue
        else:
            zr, xr, ex = (_num(r.get(cmap[k])) for k in ("rel_z", "rel_x", "ext"))
            if None in (zr, xr, ex) or not 0.5 < zr < 8 or not 3 < ex < 9:
                rej("release point missing or out of range (feet expected)")
                continue
            if cmap["hb_ft"]:
                hb, ivb = _num(r.get(cmap["hb_ft"])), _num(r.get(cmap["ivb_ft"]))
                hb = None if hb is None else hb * c_sign
            else:
                hb, ivb = _num(r.get(cmap["hb_in"])), _num(r.get(cmap["ivb_in"]))
                hb, ivb = (None if hb is None else hb * c_sign / 12.0), (None if ivb is None else ivb / 12.0)
            if hb is None or ivb is None or abs(hb) > 3 or abs(ivb) > 3:
                rej("break missing or out of range (inches expected)")
                continue
            phys = reconstruct(-abs(xr) if p["h"] == "R" else abs(xr), zr, ex, p["sp"], feed["px"], feed["pz"], hb, ivb)
            if phys is None:
                rej("no physical path fits this row")
                continue
            feed.update(pfxX=round(hb, 4), pfxZ=round(ivb, 4))
        feed.update(phys)
        tt = simview.t_to_plane(phys)
        if tt:
            feed.update(plateTime=round(tt, 4), plateTimeSZDepth=round(tt, 4))                # the selectors and result cards read the flight time
            if full:
                feed.update(pfxX=round(0.5 * phys["ax"] * tt * tt, 4), pfxZ=round(0.5 * (phys["az"] + G) * tt * tt, 4))
        par, why = simview.sim_params(feed)
        if par is None:
            rej("failed the path checks: " + re.sub(r"[-+]?\d+(\.\d+)?", "#", why or ""))
            continue
        d = (r.get(cmap["date"]) or "")[:10] if cmap["date"] else ""
        feed["_d"] = d if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else ""
        n_dates[feed["_d"]] = n_dates.get(feed["_d"], 0) + 1
        h = hashlib.sha1(f"{i}-{feed['px']}-{feed['pz']}-{feed['start_speed']}".encode()).hexdigest()[:9]
        feed["play_id"] = "imp" + h
        out["rows"].append(feed)
    ids = [r["play_id"] for r in out["rows"]]
    if len(set(ids)) != len(ids):                          # a 36-bit prefix: a collision is vanishingly rare, but an item id must be unique
        seen, keep = set(), []
        for r in out["rows"]:
            if r["play_id"] not in seen:
                seen.add(r["play_id"])
                keep.append(r)
        out["rejected"]["duplicate pitch id"] = len(ids) - len(keep)
        out["rows"] = keep
    out["dates"] = sorted((d for d in n_dates if d), reverse=True)
    kinds = {}
    for r in out["rows"]:
        kinds.setdefault(r["pitch_type"], []).append(r)
    n = len(out["rows"])
    out["summary"].update(hand=hand, total=len(raw), accepted=n, rejected=len(raw) - n, path="given" if full else "rebuilt from release point and break",
                          types={t: dict(n=len(v), usage=round(len(v) / n, 3), velo=round(sum(x["start_speed"] for x in v) / len(v), 1)) for t, v in sorted(kinds.items(), key=lambda kv: -len(kv[1]))} if n else {},
                          starts=len(out["dates"]) or 1)
    if n < MIN_ACCEPTED:
        out["error"] = f"Only {n} pitches could be drawn (need at least {MIN_ACCEPTED}). " + "; ".join(f"{c} {w}" for w, c in out["rejected"].items())
        return out
    if len(raw) - n > 0.25 * len(raw):
        out["warnings"].append(f"{len(raw) - n} of {len(raw)} rows were left out: " + "; ".join(f"{c} {w}" for w, c in out["rejected"].items()))
    out["ok"] = True
    return out


# ---------------------------------------------------------------------------- storage (in the database, so replication covers it)
def save(c, pitcher_id: int, parsed: Parsed, staff_id, note: str = "") -> int:
    rows = [{k: v for k, v in r.items()} for r in parsed["rows"]]
    with db.tx(c):
        c.execute("INSERT INTO pitch_imports(pitcher_id, rows_json, accepted, rejected, warnings_json, summary_json, note, uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?) "
                  "ON CONFLICT(pitcher_id) DO UPDATE SET rows_json=excluded.rows_json, accepted=excluded.accepted, rejected=excluded.rejected, warnings_json=excluded.warnings_json, summary_json=excluded.summary_json, "
                  "note=excluded.note, uploaded_by=excluded.uploaded_by, uploaded_at=excluded.uploaded_at",
                  (pitcher_id, json.dumps(rows, separators=(",", ":")), len(rows), parsed["summary"].get("rejected", 0), json.dumps(parsed["warnings"]), json.dumps(parsed["summary"]), (note or "")[:200], staff_id, db.now()))
        db.audit(c, "staff", staff_id, "pitches_imported", dict(pitcher_id=pitcher_id, accepted=len(rows), rejected=parsed["summary"].get("rejected", 0)))
    return len(rows)


def load(c, pitcher_id):
    r = c.execute("SELECT * FROM pitch_imports WHERE pitcher_id=?", (pitcher_id,)).fetchone()
    return None if r is None else dict(pitcher_id=pitcher_id, rows=json.loads(r["rows_json"]), summary=json.loads(r["summary_json"]), warnings=json.loads(r["warnings_json"]), uploaded_at=r["uploaded_at"], note=r["note"])


def materialize(imp: dict, pitcher_id: int, feeds_dir, max_starts: int = 6) -> list:
    """Write the imported pitches as game-feed files (one per game date) and return [(date, game_pk)] newest first, the shape playlist.pooled expects."""
    import pathlib
    feeds = pathlib.Path(feeds_dir)
    feeds.mkdir(parents=True, exist_ok=True)
    by = {}
    for r in imp["rows"]:
        by.setdefault(r.get("_d") or "0000-00-00", []).append(r)
    starts = []
    for k, (d, rows) in enumerate(sorted(by.items(), reverse=True)[:max_starts]):
        pk = 9_000_000_000 + (pitcher_id % 100_000) * 100 + k
        (feeds / f"{pk}.json").write_text(json.dumps([dict(r, pitcher=pitcher_id, game_pk=str(pk)) for r in rows]))
        starts.append((d, pk))
    return starts
