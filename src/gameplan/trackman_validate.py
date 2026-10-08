"""Validate the TrackMan adapter on MLB data. MLB pitches are written out as a TrackMan-style table with the sign conventions deliberately flipped
(all four combinations of plate-side sign and horizontal-break sign), read back through trackman.py, and compared with the MLB values the study uses.

  python -m gameplan.trackman_validate --games 777592,777586,... --hitter-csv-dir /tmp/.../hitters --hitter-id 663457 --seasons 2023,2024,2025 --work <dir>

Checks, each reported with its numbers:
  1 inferred signs equal the ones that were applied
  2 plate x, ride and run recovered (max absolute difference)
  3 pockets: agreement with the MLB per-batter zone, and with the single default zone TrackMan forces
  4 a hitter's ride and run slopes from his TrackMan-style history equal the slopes from his Statcast history
Exit code 1 if any of 1, 2, 4 fails.
"""
from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import pathlib

import numpy as np

from . import playlist as PL
from . import trackman as TM
from . import videocut as V

_TM_NAME = {"FF": "Fastball", "SI": "Sinker", "FC": "Cutter", "SL": "Slider", "ST": "Sweeper", "SV": "Slurve", "CU": "Curveball", "KC": "KnuckleCurve",
            "CH": "ChangeUp", "FS": "Splitter", "FO": "Forkball", "KN": "Knuckleball"}
_TM_CALL = {"swinging_strike": "StrikeSwinging", "swinging_strike_blocked": "StrikeSwinging", "foul_tip": "StrikeSwinging", "foul": "FoulBall",
            "hit_into_play": "InPlay", "foul_bunt": "FoulBall", "missed_bunt": "StrikeSwinging", "bunt_foul_tip": "FoulBall", "called_strike": "StrikeCalled", "ball": "BallCalled", "blocked_ball": "BallCalled"}
HEAD = ["Date", "PitchNo", "PitchUID", "GameID", "Pitcher", "PitcherId", "PitcherThrows", "Batter", "BatterId", "BatterSide", "Balls", "Strikes", "TaggedPitchType",
        "PitchCall", "RelSpeed", "InducedVertBreak", "HorzBreak", "PlateLocHeight", "PlateLocSide", "ZoneTime"]


def _csv(rows: list[dict]) -> str:
    b = io.StringIO()
    w = csv.DictWriter(b, HEAD)
    w.writeheader()
    w.writerows(rows)
    return b.getvalue()


def from_feed(pitches: list[dict], plate_flip: int, hb_flip: int) -> str:
    """MLB feed pitches as a TrackMan-style CSV. HorzBreak is raw x (not hand-normalized); its sign is the feed's pfxX (positive toward first base) times hb_flip, plate side is px times plate_flip."""
    out = []
    for i, p in enumerate(pitches):
        if p.get("type") != "pitch" or p.get("pitch_type") not in _TM_NAME or None in (p.get("px"), p.get("pz"), p.get("pfxX"), p.get("pfxZ")):
            continue
        out.append(dict(Date="2025-06-09", PitchNo=i, PitchUID=p["play_id"], GameID=p["game_pk"], Pitcher=p.get("pitcher_name"), PitcherId=p["pitcher"],
                        PitcherThrows="Right" if p["p_throws"] == "R" else "Left", Batter=p.get("batter_name"), BatterId=p["batter"],
                        BatterSide="Right" if p["stand"] == "R" else "Left", Balls=p.get("balls"), Strikes=p.get("strikes"), TaggedPitchType=_TM_NAME[p["pitch_type"]],
                        PitchCall="InPlay", RelSpeed=p.get("start_speed"), InducedVertBreak=p["pfxZ"] * 12, HorzBreak=hb_flip * p["pfxX"] * 12,
                        PlateLocHeight=p["pz"], PlateLocSide=plate_flip * p["px"], ZoneTime=p.get("plateTime")))
    return _csv(out)


def from_statcast(csv_rows: list[dict], plate_flip: int, hb_flip: int) -> str:
    """A hitter's Statcast rows as a TrackMan-style CSV. HorzBreak = pfx_x * 12 * hb_flip (x-signed, as TrackMan reports it; the Statcast column is arm-side negative for a right-handed pitcher)."""
    out = []
    for i, r in enumerate(csv_rows):
        try:
            code, call = r["pitch_type"], _TM_CALL.get(r["description"])
            vals = [float(r[k]) for k in ("pfx_x", "pfx_z", "plate_x", "plate_z", "release_speed")]
        except (KeyError, ValueError):
            continue
        if code not in _TM_NAME or not call:
            continue
        out.append(dict(Date=f"{r['_season']}-06-01", PitchNo=i, PitchUID=f"{r['_season']}-{i}", GameID=r.get("game_pk"), Pitcher="p", PitcherId=r["pitcher"],
                        PitcherThrows="Right" if r["p_throws"] == "R" else "Left", Batter="b", BatterId=r["batter"], BatterSide="Right" if r["stand"] == "R" else "Left",
                        Balls=r["balls"], Strikes=r["strikes"], TaggedPitchType=_TM_NAME[code], PitchCall=call, RelSpeed=vals[4], InducedVertBreak=vals[1] * 12,
                        HorzBreak=hb_flip * vals[0] * 12, PlateLocHeight=vals[3], PlateLocSide=plate_flip * vals[2], ZoneTime=0.4))
    return _csv(out)


def validate_feed(pitches: list[dict]) -> dict:
    res = {}
    native = {p["play_id"]: (p["px"], p["pfxZ"] * 12, PL.starter_move(p)[1]) for p in pitches if p.get("type") == "pitch" and p.get("pfxZ") is not None and p.get("pfxX") is not None
             and p.get("px") is not None and p.get("stand") in ("L", "R")}
    bsz = {}
    for p in pitches:
        if p.get("sz_top") and p.get("sz_bot"):
            bsz.setdefault(str(p["batter"]), []).append((p["sz_top"], p["sz_bot"]))
    bsz = {k: tuple(np.mean(v, axis=0)) for k, v in bsz.items()}
    for pf, hf in itertools.product((1, -1), (1, -1)):
        rows = TM.read(from_feed(pitches, pf, hf))
        sg = TM.infer_signs(rows)
        conv = TM.convert(rows, sg)
        dx = max(abs(c["px"] - native[c["play_id"]][0]) for c in conv)
        dr = max(abs(c["_ride_in"] - native[c["play_id"]][1]) for c in conv)
        dn = max(abs(c["_run_in"] - native[c["play_id"]][2]) for c in conv)
        true_pk = {p["play_id"]: V.pocket(p) for p in pitches if p.get("play_id")}
        conv_true = TM.convert(rows, sg, bsz)
        agree_true = np.mean([V.pocket(dict(c)) == true_pk[c["play_id"]] for c in conv_true if true_pk.get(c["play_id"])])
        agree_def = np.mean([V.pocket(dict(c)) == true_pk[c["play_id"]] for c in conv if true_pk.get(c["play_id"])])
        res[f"plate_flip={pf:+d} hb_flip={hf:+d}"] = dict(n=len(conv), inferred_plate=sg.plate, inferred_arm=sg.arm, signs_ok=(sg.plate == pf and sg.arm == hf),
                                                            max_dx=round(dx, 6), max_d_ride=round(dr, 6), max_d_run=round(dn, 6),
                                                            pocket_agree_per_batter_zone=round(float(agree_true), 4), pocket_agree_default_zone=round(float(agree_def), 4))
    return res


def validate_hitter(hist: list[dict], signs_rows: list[dict], batter_id: str) -> dict:
    """Slopes from the TrackMan-style history of one batter vs the same swings in Statcast form. `signs_rows` is a population-level table the signs are inferred from."""
    out = {}
    for pf, hf in itertools.product((1, -1), (1, -1)):
        # the feed's pfxX is arm-side positive and Statcast's pfx_x arm-side negative, so the same export convention needs the opposite flip
        sg = TM.infer_signs(TM.read(from_feed(signs_rows, pf, -hf)))
        tm_rows = TM.read(from_statcast(hist, pf, hf))
        hr = TM.hitter_rows(tm_rows, sg, batter_id)
        for trait, fam in (("ride", "FB"), ("run", "BRK")):
            a = PL.trait_slope(hist, fam, trait, boot=0)
            b = PL.trait_slope(hr, fam, trait, boot=0)
            out[f"{trait} plate_flip={pf:+d} hb_flip={hf:+d}"] = dict(native=round(a.get("slope", float("nan")), 4), trackman=round(b.get("slope", float("nan")), 4),
                                                                        n_native=a["n"], n_trackman=b["n"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", required=True)
    ap.add_argument("--hitter-id", type=int, required=True)
    ap.add_argument("--seasons", default="2023,2024,2025")
    ap.add_argument("--work", required=True)
    a = ap.parse_args(argv)
    work = pathlib.Path(a.work)
    pitches = []
    cache = work / "gf_val"
    cache.mkdir(parents=True, exist_ok=True)
    for g in a.games.split(","):
        f = cache / f"{g}.json"
        if not f.exists():
            f.write_text(json.dumps(V.game_pitches(g)))
        pitches += [dict(p, game_pk=g) for p in json.loads(f.read_text())]
    fv = validate_feed(pitches)
    hist = PL.hitter_history(a.hitter_id, [int(s) for s in a.seasons.split(",")], work / "hitters")
    hv = validate_hitter(hist, pitches, str(a.hitter_id))
    print(json.dumps(dict(feed=fv, hitter=hv), indent=1))
    ok = all(v["signs_ok"] and v["max_dx"] < 1e-6 and v["max_d_ride"] < 1e-6 and v["max_d_run"] < 1e-6 for v in fv.values())
    by = {}
    for k, v in hv.items():
        by.setdefault(k.split()[0], []).append(v)
    for trait, vs in by.items():
        ok &= all(abs(v["native"] - v["trackman"]) < 1e-6 and v["n_native"] == v["n_trackman"] for v in vs)
    print("PASS" if ok else "FAIL")
    (work / "trackman_validation.json").write_text(json.dumps(dict(feed=fv, hitter=hv, passed=bool(ok)), indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
