import csv
import json

import numpy as np

from gameplan import season_ledger as SL

COLS = ["id", "player", "session", "mode", "ts", "pack", "clip", "task", "options", "camera", "call", "rt_ms", "key", "correct", "pitch_type", "pocket", "px", "pz", "sz_top", "sz_bot"]


def rows_for(player, acc, n_clips, mode="assess", camera="broadcast", ts="2026-04-10T12:00:00Z", seed=0, clip_prefix="c", edge=False, session="s1"):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_clips):
        for task in ("zone", "pitch"):
            ok = rng.random() < acc
            key = ("Strike" if i % 2 else "Ball") if task == "zone" else ["FF", "SL", "CH"][i % 3]
            call = key if ok else ("Ball" if key == "Strike" else "Strike") if task == "zone" else ("SL" if key == "FF" else "FF")
            out.append(dict(id=f"{player}-{mode}-{camera}-{clip_prefix}{i}-{task}-{ts}", player=player, session=session, mode=mode, ts=ts, pack="p", clip=f"{clip_prefix}{i}", task=task, options="Strike|Ball" if task == "zone" else "FF|SL|CH",
                            camera=camera, call=call, rt_ms=400, key=key, correct=int(ok), pitch_type="FF" if task == "pitch" else "", pocket="mid-mid",
                            px=0.80 if edge else 0.0, pz=2.5, sz_top=3.5, sz_bot=1.5))
    return out


def write(tmp_path, rows, name="t.csv"):
    f = tmp_path / name
    with open(f, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS)
        w.writeheader()
        w.writerows(rows)
    return str(f)


def test_ranks_by_skill_and_marks_only_distinguishable_hitters(tmp_path):
    rows = rows_for("Ace", 0.92, 100, seed=1) + rows_for("Mid", 0.70, 100, seed=2) + rows_for("Low", 0.50, 100, seed=3)
    b = SL.boards(SL.load_any([write(tmp_path, rows)]))
    ent = b["broadcast"]["leaderboards"]["strike_ball"]
    assert [e["player"] for e in ent] == ["Ace", "Mid", "Low"] and [e["rank"] for e in ent] == [1, 2, 3]
    tiers = {e["player"]: e["tier"] for e in ent}
    assert tiers["Ace"].startswith("above") and tiers["Low"].startswith("below") and tiers["Mid"].startswith("not distinguishable")


def test_too_few_answers_are_listed_but_not_ranked(tmp_path):
    rows = rows_for("Full", 0.8, 60, seed=1) + rows_for("Thin", 0.99, 8, seed=2)
    ent = SL.boards(SL.load_any([write(tmp_path, rows)]))["broadcast"]["leaderboards"]["strike_ball"]
    thin = [e for e in ent if e["player"] == "Thin"][0]
    assert not thin["ranked"] and thin["rank"] is None and ent[-1]["player"] == "Thin" and "too few" in thin["tier"]


def test_training_answers_are_not_ranked_unless_asked(tmp_path):
    rows = rows_for("A", 0.9, 60, mode="train", seed=1) + rows_for("A", 0.5, 60, mode="assess", seed=2, clip_prefix="d")
    f = write(tmp_path, rows)
    assert SL.boards(SL.load_any([f]))["broadcast"]["players"]["A"]["strike_ball"]["accuracy"] < 0.65
    assert SL.boards(SL.load_any([f]), mode="train")["broadcast"]["players"]["A"]["strike_ball"]["accuracy"] > 0.8


def test_cameras_are_never_pooled(tmp_path):
    rows = rows_for("A", 0.9, 40, camera="broadcast", seed=1) + rows_for("A", 0.6, 40, camera="sim:hitter_eye", seed=2, clip_prefix="e") + rows_for("A", 0.7, 40, camera="sim:low_home", seed=3, clip_prefix="f")
    b = SL.boards(SL.load_any([write(tmp_path, rows)]))
    assert set(b) == {"broadcast", "drawn: hitter eye", "drawn: low home"}
    assert b["broadcast"]["players"]["A"]["strike_ball"]["n"] == 40 and b["drawn: hitter eye"]["players"]["A"]["strike_ball"]["accuracy"] < 0.75


def test_peer_adjustment_does_not_credit_easy_pitches(tmp_path):
    # EasyOnly sees pitches everyone gets right; the others see hard pitches (60%) and easy ones; EasyOnly's raw accuracy is high, vs_peers is about zero
    rows = []
    for p in ("P1", "P2", "P3", "P4", "P5", "EasyOnly"):
        rows += rows_for(p, 0.97, 40, seed=sum(map(ord, p)), clip_prefix="easy", edge=False)
    for p in ("P1", "P2", "P3", "P4", "P5"):
        rows += rows_for(p, 0.60, 40, seed=sum(map(ord, p)) + 7, clip_prefix="hard", edge=True)
    ent = {e["player"]: e for e in SL.boards(SL.load_any([write(tmp_path, rows)]))["broadcast"]["leaderboards"]["strike_ball"]}
    others = sum(ent[f"P{i}"]["accuracy"] for i in range(1, 6)) / 5
    assert ent["EasyOnly"]["accuracy"] > others + 0.08                                      # raw accuracy flatters him (measured over 200 seeds: gap at least 0.10)
    assert abs(ent["EasyOnly"]["vs_peers"]) < 0.10                                          # against peers on the same pitches he is average (measured max 0.08)


def test_edge_metric_and_pitch_lift_over_chance_and_trend(tmp_path):
    rows = rows_for("A", 0.9, 60, seed=1, edge=True, ts="2026-04-10T12:00:00Z") + rows_for("A", 0.5, 60, seed=2, edge=True, ts="2026-05-10T12:00:00Z", clip_prefix="m")
    led = SL.boards(SL.load_any([write(tmp_path, rows)]))["broadcast"]["players"]["A"]
    assert led["edge"]["n"] == 120 and abs(led["pitch_type"]["chance_baseline"] - 0.333) < 0.001 and led["pitch_type"]["lift_over_chance"] > 0.2
    assert [t["month"] for t in led["trend"]] == ["2026-04", "2026-05"] and led["trend"][0]["zone"]["accuracy"] > led["trend"][1]["zone"]["accuracy"] + 0.25


def test_jsonl_and_duplicate_ids_load_once_and_html_renders(tmp_path):
    rows = rows_for("A", 0.8, 40, seed=1)
    jl = tmp_path / "t.jsonl"
    jl.write_text("\n".join(json.dumps(r) for r in rows + rows[:10]))
    loaded = SL.load_any([str(jl)])
    assert len(loaded) == len(rows)
    page = SL.render_html(SL.boards(loaded))
    assert "Strike or ball" in page and "not distinguishable" in page or "above group" in page or "below group" in page
    assert SL.render_html({}).count("No answers") == 1
