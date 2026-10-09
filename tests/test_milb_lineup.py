from gameplan import milb_lineup as ML


def pitch(pk, date, pitcher, team, batter, stand="R", inning=1, ab=1, n=1, **kw):
    return dict(game_pk=str(pk), _date=date, _season=2025, pitcher=pitcher, pitcher_name=f"P{pitcher}", team_fielding_id=team, batter=batter, batter_name=f"B{batter}", stand=stand, inning=inning,
                ab_number=ab, pitch_number=n, type="pitch", pitch_type="FF", px=0.0, pz=2.5, sz_top=3.5, sz_bot=1.5, start_speed=93, pfxX=0.5, pfxZ=1.2, p_throws="R", strikes=0,
                balls=0, plateTime=0.4, play_id=f"{pk}-{pitcher}-{ab}-{n}", description="Ball", **kw)


def feed():
    rows = []
    for g, d in enumerate(["2025-05-01", "2025-05-06", "2025-05-11", "2025-05-16"], start=1):
        rows += [pitch(g, d, 1, 10, 100 + g, ab=1, n=1), pitch(g, d, 1, 10, 100 + g, ab=1, n=2),
                 pitch(g, d, 2, 10, 200, inning=7), pitch(g, d, 3, 20, 300, inning=1, ab=1)]      # pitcher 2 relieves, pitcher 3 starts for the other team
    return rows


def test_starter_is_whoever_threw_the_first_pitch_not_the_reliever():
    s = ML.game_starters(feed())
    assert {v[1] for k, v in s.items() if k[1] == 10} == {1} and {v[1] for k, v in s.items() if k[1] == 20} == {3}


def test_plan_uses_only_earlier_starts_and_the_planned_games_lineup():
    r = ML.plan(feed(), pitcher_id=1, n_starts=3, min_starts=4)
    assert r["planned_game"] == "4" and r["starts_pooled"] == ["2025-05-11", "2025-05-06", "2025-05-01"]
    assert [h["id"] for h in r["hitters"]] == [104]                          # the batter who faced him in the last start only
    assert r["pool"] == 6


def test_refuses_a_pitcher_with_too_few_starts():
    import pytest
    with pytest.raises(ValueError):
        ML.plan(feed(), pitcher_id=1, min_starts=9)
