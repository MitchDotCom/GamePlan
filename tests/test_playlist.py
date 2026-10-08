from gameplan import playlist as PL



def row(pt, px, pz, age, pid, stand="L"):
    return dict(type="pitch", play_id=pid, plateTime=0.45, pitcher=1, pitch_type=pt, px=px, pz=pz, sz_top=3.5, sz_bot=1.5, stand=stand,
                p_throws="R", _age=age, game_pk=str(100 + age))


def test_recency_weighting_changes_usage_rank():
    # old start: 4 high-away fastballs; recent start: 3 low-in sliders. Recent start counts 1.0 each, the old one 0.5**(3/2) each.
    rows = [row("FF", -0.6, 3.2, 3, f"o{i}") for i in range(4)] + [row("SL", 0.6, 1.6, 0, f"r{i}") for i in range(3)]
    assert PL.usage(rows, dict(stand="L"), 1) == [("BRK", "low-in")]


def test_hitter_cost_picks_costliest_offered_shape_and_ignores_unoffered():
    rows = [row("FF", -0.6, 3.2, 0, f"a{i}") for i in range(5)] + [row("SL", 0.6, 1.6, 0, f"b{i}") for i in range(5)] + [row("CH", 0.0, 2.5, 0, "c0")] + [row("FF", -0.6, 3.2, 0, f"e{i}") for i in range(30)]
    hdr = "pitch_type,delta_run_exp,plate_x,plate_z,sz_top,sz_bot,stand,p_throws\n"
    lines = ["SL,-0.3,0.6,1.6,3.5,1.5,L,R"] * 60 + ["FF,0.0,-0.6,3.2,3.5,1.5,L,R"] * 60 + ["CH,-0.9,0.0,2.5,3.5,1.5,L,R"] * 60 + ["SL,0.1,0.6,1.6,3.5,1.5,L,L"] * 50
    got = PL.hitter_cost(rows, dict(stand="L", rows=PL.read_rows(hdr + "\n".join(lines), 2025)), 3)
    assert got[0] == ("BRK", "low-in")          # costliest among offered shapes
    assert ("OFF", "mid-mid") not in got        # the changeup is far costlier for him but is under 5% of the starter's pitches


def test_playlist_selects_only_requested_side_and_shapes():
    rows = [row("FF", -0.6, 3.2, 0, "a"), row("FF", -0.6, 3.2, 1, "b"), row("SL", 0.6, 1.6, 0, "c"), row("FF", -0.6, 3.2, 0, "d", stand="R")]
    pl = PL.playlist("usage", rows, dict(stand="L", name="x"), n=1, limit=5)
    assert pl["shapes"] == [("FB", "high-away")]
    assert [p["play_id"] for p in pl["pitches"]] == ["a", "b"]


def test_count_bucket_and_thin_bucket_refuses():
    def cp(b, k, i):
        return dict(row("FF", -0.6, 3.2, 0, f"p{i}"), balls=b, strikes=k)
    assert [PL.count_bucket(dict(balls=b, strikes=k)) for b, k in ((0, 0), (2, 1), (1, 1), (0, 1), (1, 2))] == ["first", "ahead", "even", "behind", "two_strike"]
    rows = [cp(0, 0, i) for i in range(30)] + [cp(3, 0, 99)]
    ok = PL.playlist("usage", rows, dict(stand="L", name="x"), n=1, limit=5, bucket="first")
    assert ok["shapes"] == [("FB", "high-away")] and "descriptive" in ok["evidence"]
    thin = PL.playlist("usage", rows, dict(stand="L", name="x"), n=1, limit=5, bucket="ahead")
    assert thin["pitches"] == [] and "only 1 pitches to LHH" in thin["why"]
    assert "thin" in PL.EVIDENCE["ride"] and "validated" in PL.playlist("usage", rows, dict(stand="L", name="x"))["evidence"]


def test_milb_cache_survives_partial_file(tmp_path, monkeypatch):
    from gameplan import milb_feed as MF
    (tmp_path / "123.json").write_text('{"meta": {"game_pk"')          # a killed run left half a file
    monkeypatch.setattr(MF.V, "game_pitches", lambda pk: [dict(type="pitch", pitch_type="FF", start_speed=90, px=0, pz=2, pfxX=1, pfxZ=1)])
    meta = MF.fetch_game("2025-06-01", 123, tmp_path)
    assert meta["tracked"] == 1 and MF.load(tmp_path)[0]["game_pk"] == "123"
