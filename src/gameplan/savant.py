"""Baseball Savant Statcast search: fetch, parse to swing-level rows, and fit a shrunk
per-hitter xwOBA-by-location model that plugs into plan.generate_grid_plan.

Network: fetch_csv needs baseballsavant.mlb.com reachable. Everything else works on a local CSV."""
from __future__ import annotations

import csv
import io
import math
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

SEARCH_URL = "https://baseballsavant.mlb.com/statcast_search/csv"

SWING_DESCRIPTIONS = {
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "foul_bunt",
    "hit_into_play", "missed_bunt", "bunt_foul_tip",
}
WHIFF_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}


def build_url(batter_id: int, season: int, pitch_types: Optional[Iterable[str]] = None) -> str:
    """Savant search URL for one batter-season, pitch-level rows."""
    pt = "".join(f"{p}|" for p in pitch_types) if pitch_types else ""
    params = {
        "all": "true", "hfSea": f"{season}|", "hfPT": pt, "hfGT": "R|",
        "player_type": "batter", "batters_lookup[]": str(batter_id),
        "min_pitches": "0", "min_results": "0", "group_by": "name",
        "sort_col": "pitches", "sort_order": "desc", "type": "details",
    }
    return SEARCH_URL + "?" + urllib.parse.urlencode(params)


def fetch_csv(url: str, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "gameplan/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig")


def _f(v: str | None) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "null", "NA") else None
    except ValueError:
        return None


def approach_angle(row: dict) -> Optional[float]:
    """Vertical approach angle (deg, negative = descending) at the front of the plate from
    Statcast release kinematics. Uses vy0, vz0, ay, az, y0=50 ft, plate front at y=17/12 ft."""
    vy0, vz0, ay, az = (_f(row.get(k)) for k in ("vy0", "vz0", "ay", "az"))
    if None in (vy0, vz0, ay, az) or ay == 0:
        return None
    disc = vy0 * vy0 - 2 * ay * (50.0 - 17.0 / 12.0)
    if disc <= 0:
        return None
    vy_f = -math.sqrt(disc)
    t = (vy_f - vy0) / ay
    vz_f = vz0 + az * t
    return math.degrees(math.atan2(vz_f, -vy_f))


@dataclass(frozen=True)
class SwingRow:
    batter: str
    pitch_type: str
    x: float
    z: float
    ivb: Optional[float]
    vaa: Optional[float]
    velo: Optional[float]
    value: float          # xwOBA on contact; 0 on whiff / foul
    whiff: bool


def parse_swings(csv_text: str) -> list[SwingRow]:
    """Swing-level rows only. Value per swing: xwOBA (speed/angle) on balls in play, 0 on whiffs
    and fouls. Coordinates: plate_x is catcher's view already; plate_z is feet off the ground."""
    out = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        desc = (row.get("description") or "").strip()
        if desc not in SWING_DESCRIPTIONS:
            continue
        x, z, pt = _f(row.get("plate_x")), _f(row.get("plate_z")), row.get("pitch_type")
        if x is None or z is None or not pt:
            continue
        if desc == "hit_into_play":
            v = _f(row.get("estimated_woba_using_speedangle"))
            if v is None:
                v = _f(row.get("woba_value"))
            if v is None:
                continue
        else:
            v = 0.0
        pfx_z = _f(row.get("pfx_z"))
        out.append(SwingRow(
            batter=str(row.get("batter") or ""), pitch_type=pt, x=x, z=z,
            ivb=pfx_z * 12.0 if pfx_z is not None else None,
            vaa=approach_angle(row), velo=_f(row.get("release_speed")),
            value=v, whiff=desc in WHIFF_DESCRIPTIONS,
        ))
    return out


class ShrunkXwoba:
    """Cell value = (hitter_sum + k * league_mean) / (hitter_n + k), per pitch type and grid cell.

    League prior comes from all swings in the data you pass, so pass more than one hitter.
    k is the number of pseudo-swings of league evidence. Cells with no league data fall back to the
    pitch type's overall mean, then to the global mean."""

    def __init__(self, hitter_swings: list[SwingRow], league_swings: list[SwingRow],
                 k: float = 30.0, cell_ft: float = 4.0 / 12.0):
        self.k, self.cell = k, cell_ft
        self._h = self._agg(hitter_swings)
        self._l = self._agg(league_swings)
        self._lt = self._agg_type(league_swings)
        allv = [s.value for s in league_swings]
        self._global = sum(allv) / len(allv) if allv else 0.0
        hv = [s.value for s in hitter_swings]
        self.hitter_baseline = sum(hv) / len(hv) if hv else self._global

    def _key(self, x: float, z: float) -> tuple[int, int]:
        return math.floor(x / self.cell), math.floor(z / self.cell)

    def _agg(self, rows):
        d: dict = defaultdict(lambda: [0.0, 0])
        for s in rows:
            a = d[(s.pitch_type,) + self._key(s.x, s.z)]
            a[0] += s.value
            a[1] += 1
        return d

    @staticmethod
    def _agg_type(rows):
        d: dict = defaultdict(lambda: [0.0, 0])
        for s in rows:
            a = d[s.pitch_type]
            a[0] += s.value
            a[1] += 1
        return d

    def samples(self, x: float, z: float, pt: str) -> int:
        return self._h.get((pt,) + self._key(x, z), [0.0, 0])[1]

    def __call__(self, x: float, z: float, pt: str, ivb: float = 0.0) -> float:
        key = (pt,) + self._key(x, z)
        ls, ln = self._l.get(key, [0.0, 0])
        if ln >= 10:
            prior = ls / ln
        elif pt in self._lt:
            ts, tn = self._lt[pt]
            prior = ts / tn
        else:
            prior = self._global
        hs, hn = self._h.get(key, [0.0, 0])
        return (hs + self.k * prior) / (hn + self.k)


def fit_hitter_model(csv_text: str, batter_id: str, k: float = 30.0) -> ShrunkXwoba:
    rows = parse_swings(csv_text)
    return ShrunkXwoba([r for r in rows if r.batter == str(batter_id)], rows, k=k)


def main(argv: list[str] | None = None) -> int:
    """python -m gameplan.savant --batter 665742 --season 2025 --out data/665742_2025.csv"""
    import argparse
    import pathlib
    ap = argparse.ArgumentParser()
    ap.add_argument("--batter", type=int, required=True, help="MLBAM player id")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--pitch-types", nargs="*")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    text = fetch_csv(build_url(a.batter, a.season, a.pitch_types))
    path = pathlib.Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"wrote {len(text.splitlines()) - 1} pitches to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
