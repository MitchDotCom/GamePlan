import numpy as np
import pytest

from gameplan import playlist as PL
from gameplan import trackman as TM
from gameplan.trackman_validate import HEAD, _csv


def table(plate_flip=1, hb_flip=1, n=800, seed=0):
    """Synthetic export: batters get more pitches away than in; right-handed pitchers' fastballs run toward first base (+x), left-handed the mirror."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        bs = "Right" if i % 2 else "Left"
        th = "Right" if (i // 2) % 2 else "Left"
        away = abs(rng.normal(0.3, 0.4)) * (1 if rng.random() < 0.7 else -1)           # mostly away
        x_1b = away if bs == "Right" else -away                                         # + = first base side
        hb_1b = (8 if th == "Right" else -8) + rng.normal(0, 1)                         # arm-side = toward 1B for RHP
        rows.append(dict(Date="2025-06-01", PitchNo=i, PitchUID=f"u{i}", GameID="g1", Pitcher="P", PitcherId=7, PitcherThrows=th, Batter="B", BatterId=9,
                         BatterSide=bs, Balls=0, Strikes=0, TaggedPitchType="Fastball", PitchCall="StrikeSwinging", RelSpeed=93, InducedVertBreak=16,
                         HorzBreak=hb_flip * hb_1b, PlateLocHeight=2.5, PlateLocSide=plate_flip * x_1b, ZoneTime=0.4))
    return _csv(rows), rows


@pytest.mark.parametrize("pf,hf", [(1, 1), (1, -1), (-1, 1), (-1, -1)])
def test_signs_inferred_and_values_recovered(pf, hf):
    text, _ = table(pf, hf)
    rows = TM.read(text)
    sg = TM.infer_signs(rows)
    assert (sg.plate, sg.arm) == (pf, hf)
    conv = TM.convert(rows, sg)
    # right-handed batter: toward first base is away, so away == + for RHB; sign convention must be recovered regardless of how the export is signed
    for c, r in zip(conv, TM.read(text)):
        assert c["px"] == pytest.approx(pf * float(r["PlateLocSide"]))
    rhb_rhp = [c for c in conv if c["stand"] == "R" and c["p_throws"] == "R"]
    assert all(c["_run_in"] > 0 for c in rhb_rhp)      # arm-side run vs a right-handed batter is away
    lhb_rhp = [c for c in conv if c["stand"] == "L" and c["p_throws"] == "R"]
    assert all(c["_run_in"] < 0 for c in lhb_rhp)      # the same pitch runs in on a lefty


def test_missing_column_and_undecidable_signs_refuse():
    text, rows = table()
    with pytest.raises(ValueError, match="missing columns"):
        TM.read(text.replace("InducedVertBreak", "Nope"))
    with pytest.raises(ValueError, match="cannot infer plate-side"):
        TM.infer_plate_sign(TM.read(_csv(rows[:20])))
    flat = [dict(r, PlateLocSide=0.1) for r in rows]
    with pytest.raises(ValueError, match="cannot infer plate-side"):
        TM.infer_plate_sign(TM.read(_csv(flat)))
    both_same = [dict(r, HorzBreak=8.0) for r in rows]
    with pytest.raises(ValueError, match="horizontal-break"):
        TM.infer_arm_sign(TM.read(_csv(both_same)))


def test_pool_takes_last_starts_before_date_and_tags_age():
    pitches = [dict(pitcher="7", _date=d, game_pk=d, play_id=d) for d in ("2025-06-01", "2025-06-06", "2025-06-11", "2025-06-16")]
    got = TM.pool(pitches, 7, 2, "2025-06-12")
    assert [(p["_date"], p["_age"]) for p in got] == [("2025-06-11", 0), ("2025-06-06", 1)]


def test_trackman_rows_drive_playlists():
    text, _ = table(n=600)
    rows = TM.read(text)
    sg = TM.infer_signs(rows)
    pitches = TM.pool(TM.convert(rows, sg), 7, 3, "2025-07-01")
    assert PL.usage(pitches, dict(stand="R"), 2)             # usage works from TrackMan rows
    assert PL.starter_move(pitches[0]) == (pitches[0]["_ride_in"], pitches[0]["_run_in"])
    assert PL.hitter_cost(pitches, dict(stand="R", rows=[]), 3) == []   # no run values in TrackMan: refuses, does not rank arbitrarily
