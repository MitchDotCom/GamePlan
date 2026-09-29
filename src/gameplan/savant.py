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
    date: str             # game_date, ISO so it sorts chronologically
    pitch_type: str
    x: float
    z: float
    ivb: Optional[float]
    vaa: Optional[float]
    velo: Optional[float]
    xwoba: Optional[float]   # xwOBA (speed/angle) on balls in play only; None on whiff / foul
    whiff: bool


def parse_swings(csv_text: str) -> list[SwingRow]:
    """Swing-level rows only. Fouls stay in (they are contact, no batted-ball value).
    Coordinates: plate_x is catcher's view already; plate_z is feet off the ground."""
    out = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        desc = (row.get("description") or "").strip()
        if desc not in SWING_DESCRIPTIONS:
            continue
        x, z, pt = _f(row.get("plate_x")), _f(row.get("plate_z")), row.get("pitch_type")
        if x is None or z is None or not pt:
            continue
        xw = None
        if desc == "hit_into_play":
            xw = _f(row.get("estimated_woba_using_speedangle"))
            if xw is None:
                xw = _f(row.get("woba_value"))
            if xw is None:
                continue
        pfx_z = _f(row.get("pfx_z"))
        out.append(SwingRow(
            batter=str(row.get("batter") or ""), date=row.get("game_date") or "",
            pitch_type=pt, x=x, z=z,
            ivb=pfx_z * 12.0 if pfx_z is not None else None,
            vaa=approach_angle(row), velo=_f(row.get("release_speed")),
            xwoba=xw, whiff=desc in WHIFF_DESCRIPTIONS,
        ))
    return out


def contact_quality(swings: Iterable[SwingRow]) -> Optional[float]:
    """Whiff-adjusted contact quality: (1 - whiff rate) * mean xwOBA on balls in play.
    Raw (unshrunk). None if there are no swings or no batted balls."""
    n = w = bip = 0
    xs = 0.0
    for s in swings:
        n += 1
        w += s.whiff
        if s.xwoba is not None:
            bip += 1
            xs += s.xwoba
    if n == 0 or bip == 0:
        return None
    return (1 - w / n) * (xs / bip)


class ContactQualityModel:
    """Per pitch type and grid cell: CQ = (1 - whiff rate) * xwOBA on balls in play, where each
    component is shrunk separately toward the league value for that cell:

        whiff  = (hitter_whiffs + k_swing * league_whiff) / (hitter_swings + k_swing)
        xwOBAcon = (hitter_xw   + k_bip   * league_xw)    / (hitter_bip    + k_bip)

    Cells with under MIN_LEAGUE league swings fall back to the pitch type's average, then global.
    Pass many hitters as league_swings. Callable as (x, z, pitch_type, ivb) so it drops into
    plan.generate_grid_plan."""

    MIN_LEAGUE = 10

    def __init__(self, hitter_swings: list[SwingRow], league_swings: list[SwingRow],
                 k_swing: float = 30.0, k_bip: float = 15.0, cell_ft: float = 4.0 / 12.0):
        self.k_swing, self.k_bip, self.cell = k_swing, k_bip, cell_ft
        self._h = self._agg(hitter_swings, cell=True)
        self._l = self._agg(league_swings, cell=True)
        self._lt = self._agg(league_swings, cell=False)
        self._g = self._sum(league_swings)
        hv = self._sum(hitter_swings)
        cq = contact_quality(hitter_swings)
        self.hitter_cq = cq if cq is not None else self._rate(self._g)[2]
        self.hitter_xwobacon = hv[3] / hv[2] if hv[2] else self._rate(self._g)[1]

    # accumulators: [swings, whiffs, bip, xwoba_sum]
    @staticmethod
    def _sum(rows):
        a = [0, 0, 0, 0.0]
        for s in rows:
            a[0] += 1
            a[1] += s.whiff
            if s.xwoba is not None:
                a[2] += 1
                a[3] += s.xwoba
        return a

    def _key(self, x: float, z: float) -> tuple[int, int]:
        return math.floor(x / self.cell), math.floor(z / self.cell)

    def _agg(self, rows, cell: bool):
        d: dict = defaultdict(lambda: [0, 0, 0, 0.0])
        for s in rows:
            key = (s.pitch_type,) + self._key(s.x, s.z) if cell else s.pitch_type
            a = d[key]
            a[0] += 1
            a[1] += s.whiff
            if s.xwoba is not None:
                a[2] += 1
                a[3] += s.xwoba
        return d

    @staticmethod
    def _rate(a):
        """(whiff rate, xwOBAcon, CQ) from an accumulator; safe on empties."""
        w = a[1] / a[0] if a[0] else 0.25
        xc = a[3] / a[2] if a[2] else 0.35
        return w, xc, (1 - w) * xc

    def samples(self, x: float, z: float, pt: str) -> int:
        return self._h.get((pt,) + self._key(x, z), [0])[0]

    def _prior(self, key, pt):
        a = self._l.get(key)
        if a is None or a[0] < self.MIN_LEAGUE:
            a = self._lt.get(pt, self._g)
        return self._rate(a)

    def __call__(self, x: float, z: float, pt: str, ivb: float = 0.0) -> float:
        key = (pt,) + self._key(x, z)
        lw, lx, _ = self._prior(key, pt)
        h = self._h.get(key, [0, 0, 0, 0.0])
        whiff = (h[1] + self.k_swing * lw) / (h[0] + self.k_swing)
        xc = (h[3] + self.k_bip * lx) / (h[2] + self.k_bip)
        return (1 - whiff) * xc


def fit_hitter_model(csv_text: str, batter_id: str, **kw) -> ContactQualityModel:
    rows = parse_swings(csv_text)
    return ContactQualityModel([r for r in rows if r.batter == str(batter_id)], rows, **kw)


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
