from gameplan import videocut as V


def row(pt, px, pz, stand="L", pid="x"):
    return dict(type="pitch", play_id=pid, plateTime=0.45, pitcher_name="A Pitcher", pitch_type=pt, px=px, pz=pz, sz_top=3.5, sz_bot=1.5, stand=stand)


def test_top_shapes_usage_and_side():
    rows = [row("FF", -0.6, 3.2)] * 3 + [row("SL", 0.6, 1.6)] * 2 + [row("CH", 0.0, 2.5)] + [row("FF", 0.0, 2.5, stand="R")] * 5
    top = V.top_shapes(rows, "pitcher", "L", 2)
    assert top == [("FB", "high-away"), ("BRK", "low-in")]
    assert V.top_shapes(rows, "pitcher", "R", 1) == [("FB", "mid-mid")]


def test_select_filters_by_shape_and_side():
    rows = [row("FF", -0.6, 3.2, pid="a"), row("SL", 0.6, 1.6, pid="b"), row("FF", -0.6, 3.2, "R", pid="c")]
    got = V.select(rows, pitcher="pitcher", stand="L", shapes=(("FB", "high-away"),))
    assert [p["play_id"] for p in got] == ["a"]
