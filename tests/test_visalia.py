import pathlib

import pytest

from gameplan import visalia as VS


def pitches():
    return [dict(play_id=f"u{i}", _date="2026-05-01", inning=str(1 + i // 4), pa=str(1 + i // 2), pitch_of_pa=str(1 + i % 2)) for i in range(8)]


def test_name_pattern_unique_match_and_refusals(tmp_path):
    clips = [tmp_path / n for n in ("20260501_inn1_pa1_p1.mp4", "20260501_inn1_pa1_p2.mov", "bad_name.mp4", "20260501_inn9_pa9_p9.mp4")]
    pat = r"(?P<date>\d{8})_inn(?P<inning>\d+)_pa(?P<pa>\d+)_p(?P<pitch>\d+)"
    got, problems = VS.match_by_name(clips, pitches(), pat)
    assert got == {"20260501_inn1_pa1_p1": "u0", "20260501_inn1_pa1_p2": "u1"}
    names = dict(problems)
    assert "does not match" in names["bad_name.mp4"] and "0 pitches match" in names["20260501_inn9_pa9_p9.mp4"]


def test_ambiguous_pattern_is_refused(tmp_path):
    got, problems = VS.match_by_name([tmp_path / "20260501_inn1.mp4"], pitches(), r"(?P<date>\d{8})_inn(?P<inning>\d+)")
    assert got == {} and "4 pitches match" in problems[0][1]


def test_manifest_read_and_requires_a_join(tmp_path):
    m = tmp_path / "m.csv"
    m.write_text("clip,pitch_uid\nclipA.mp4,u3\nclipB,u4\n")
    assert VS.read_manifest(m) == {"clipA": "u3", "clipB": "u4"}
    with pytest.raises(ValueError, match="manifest or --name-pattern"):
        VS.build("x", 1, "2026-01-01", 3, 2, "L", "usage", tmp_path, tmp_path, None)
