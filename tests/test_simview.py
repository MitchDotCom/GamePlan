import copy
import json
import pathlib

import pytest

from gameplan import simview as S

ROW = dict(x0=-1.22, y0=50.0059, z0=5.27, vx0=5.876, vy0=-134.6, vz0=-4.957, ax=-16.359, ay=32.388, az=-17.984, start_speed=92.6, sz_top=3.4, sz_bot=1.6, stand="R", p_throws="R")


def good(**over):
    r = dict(ROW, **over)
    par = {k: r[k] for k in S.FIELDS}
    t = S.t_to_plane(par)
    x, y, z = S.position(par, t)
    return dict(r, px=x, pz=z, plateTimeSZDepth=t)


def test_a_consistent_row_becomes_a_drawn_pitch():
    par, why = S.sim_params(good())
    assert why is None and abs(par["t_zone"] - S.t_to_plane({k: ROW[k] for k in S.FIELDS})) < 1e-4
    x, y, z = S.position(par, par["t_zone"])
    assert abs(x - par["px"]) < 0.005 and abs(z - par["pz"]) < 0.005 and abs(y - S.Y_PLATE) < 1e-3


@pytest.mark.parametrize("change,needle", [
    (dict(x0=None), "missing"),
    (dict(vy0="nan"), "missing"),
    (dict(y0=40.0), "release plane"),
    (dict(vy0=-60.0), "zone time"),                                    # a 41 mph pitch cannot reach the plate in 0.3 to 0.6 s
    (dict(plateTimeSZDepth=0.45), "disagrees"),
    (dict(px=0.9), "crosses at"),                                      # the key would say ball while the drawing says strike
    (dict(pz=0.5), "crosses at"),
    (dict(start_speed=80.0), "speed"),
    (dict(sz_top=None), "missing"),
])
def test_each_gate_rejects_its_corruption(change, needle):
    r = dict(good(), **change)
    par, why = S.sim_params(r)
    assert par is None and needle in why


def test_real_rows_if_cached_all_pass_or_say_why():
    f = pathlib.Path("/tmp/claude-0/app/work/feeds")
    files = sorted(f.glob("*.json"))[:2] if f.exists() else []
    if not files:
        pytest.skip("no cached feeds in this environment")
    rows = [p for fl in files for p in json.loads(fl.read_text()) if p.get("type") == "pitch"]
    res = [S.sim_params(p) for p in rows]
    assert all(par is not None or why for par, why in res) and sum(par is not None for par, _ in res) > 0.95 * len(rows)


def test_cutter_returns_no_file_and_release_zero():
    r = S.sim_cutter(good())
    assert r["release"] == 0.0 and r["sim"]["t_zone"] > 0.3 and S.sim_cutter(dict(good(), px=5.0)) is None


def test_separation_is_zero_for_identical_pitches_and_grows_with_time():
    a = [S.sim_params(good())[0]]
    assert S.separation({"A": a, "B": a}, 0.2) == {"A-B": 0.0}
    b = [S.sim_params(good(ax=-5.0))[0]]                                # less tail: the paths part company as the ball travels
    early, late = S.separation({"A": a, "B": b}, 0.1)["A-B"], S.separation({"A": a, "B": b}, 0.3)["A-B"]
    assert 0 < early < late
