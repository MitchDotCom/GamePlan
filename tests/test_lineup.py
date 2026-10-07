from gameplan import lineup as LU
from gameplan import playlist as PL


def row(pt, px, pz, age, pid, stand="L"):
    return dict(type="pitch", play_id=pid, plateTime=0.45, pitcher=1, pitch_type=pt, px=px, pz=pz, sz_top=3.5, sz_bot=1.5, stand=stand,
                p_throws="R", _age=age, game_pk=str(100 + age))


def test_plan_hitter_survives_missing_history(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(PL, "hitter_history", boom)
    rows = [row("FF", -0.6, 3.2, 0, f"a{i}") for i in range(6)]
    p = LU.plan_hitter(rows, dict(id=1, name="X", stand="L"), [2025], tmp_path)
    assert "history not fetched" in p["error"]
    assert p["lists"]["usage"]["status"] == "ok" and p["lists"]["usage"]["shapes"] == [["FB", "high-away"]]
    assert p["lists"]["run"]["status"] == "skipped"


def test_markdown_has_one_row_per_hitter():
    plans = [dict(id=1, name="A", stand="L", lists=dict(usage=dict(status="ok", shapes=[["FB", "high-away"]], pitches=["x"]), run=dict(status="none", shapes=[], pitches=[], why="n"))),
             dict(id=2, name="B", stand="R", lists={})]
    md = LU.to_markdown("S", dict(starts=3, before="2025-06-01", pool=100, seasons="2023 to 2025"), plans)
    assert md.count("\n| A |") == 1 and md.count("\n| B |") == 1 and "FB-high-away" in md and "no list: n" in md
