import csv

import numpy as np

from gameplan import recognition_profile as RP

COLS = ["player", "session", "mode", "ts", "clip", "task", "pause_ms", "call", "rt_ms", "key", "correct", "pitch_type", "family", "pocket", "px", "pz", "sz_top", "sz_bot", "speed",
        "stand", "p_throws", "release_frame"]


def make(path, player="A", session="s1", n=600, base=0.75, weak=("low-away", 0.35), seed=1, task="zone"):
    rng = np.random.default_rng(seed)
    rows = []
    pockets = [f"{h}-{s}" for h in ("high", "mid", "low") for s in ("in", "mid", "away")]
    for i in range(n):
        pk = pockets[i % 9]
        key = "Strike" if rng.random() < 0.5 else "Ball"
        acc = weak[1] if pk == weak[0] else base
        ok = rng.random() < acc
        call = key if ok else ("Ball" if key == "Strike" else "Strike")
        rows.append(dict(player=player, session=session, mode="assess", ts="t", clip=f"c{i}", task=task, pause_ms=100, call=call, rt_ms=int(rng.normal(450, 60)), key=key, correct=int(ok),
                         pitch_type="FF", family="FB", pocket=pk, px=0.2, pz=2.5, sz_top=3.5, sz_bot=1.5, speed=93, stand="R", p_throws="R", release_frame=400))
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, COLS)
        if f.tell() == 0:
            w.writeheader()
        w.writerows(rows)


def test_sdt_basic_and_no_infinities():
    perfect = RP.sdt(50, 50, 0, 50)
    assert perfect["d_prime"] > 3 and np.isfinite(perfect["d_prime"])
    guess = RP.sdt(25, 50, 25, 50)
    assert abs(guess["d_prime"]) < 0.01 and abs(guess["criterion"]) < 0.01
    assert RP.sdt(5, 5, 0, 0)["d_prime"] is None


def test_profile_recovers_known_weak_pocket_and_overall_accuracy(tmp_path):
    f = tmp_path / "t.csv"
    make(f)
    pr = RP.profile(RP.load([str(f)]), "A")
    z = pr["zone"]["summary"]
    assert 0.68 < z["accuracy"] < 0.78 and z["d_prime"] > 1.0 and z["majority_baseline"] < 0.6
    names = [c[0] for c in pr["zone"]["weak_cells"]["by_pocket"]]
    assert names == ["low-away"]                         # only the planted weakness, no false weak cells here
    assert pr["pitch"]["summary"]["n"] == 0


def test_small_cells_are_hidden_not_guessed(tmp_path):
    f = tmp_path / "t.csv"
    make(f, n=40)
    pr = RP.profile(RP.load([str(f)]), "A")
    assert all(v["accuracy"] is None for v in pr["zone"]["by_pocket"].values())


def test_compare_detects_improvement_and_refuses_thin_sessions(tmp_path):
    f = tmp_path / "t.csv"
    make(f, session="pre", base=0.65, weak=("none", 0), seed=2, n=240)
    make(f, session="post", base=0.85, weak=("none", 0), seed=3, n=240)
    rows = RP.load([str(f)])
    c = RP.compare(rows, "A", "zone", "pre", "post")
    assert c["ok"] and c["change_d_prime"] > 0.5 and c["ci"][0] > 0
    assert not RP.compare(rows, "A", "zone", "pre", "missing")["ok"]


def test_html_and_edge_buckets(tmp_path):
    f = tmp_path / "t.csv"
    make(f)
    pr = RP.profile(RP.load([str(f)]), "A")
    page = RP.render_html(pr)
    assert "Strike or ball" in page and "low-away" in page
    assert RP.edge_bucket(dict(px=1.2, pz=2.5, sz_top=3.5, sz_bot=1.5)).startswith("outside")
    assert RP.edge_bucket(dict(px=0.0, pz=2.5, sz_top=3.5, sz_bot=1.5)).startswith("inside, deeper")


def test_pitch_task_scores_against_the_offered_choices_and_lists_confusions(tmp_path):
    f = tmp_path / "t.csv"
    cols = COLS + ["options"]
    rng = np.random.default_rng(5)
    rows = []
    for i in range(120):
        key = ["FF", "SL", "CH"][i % 3]
        ok = rng.random() < 0.7
        call = key if ok else ("SL" if key == "FF" else "FF")
        rows.append(dict(player="A", session="s1", mode="train", ts="t", clip=f"c{i}", task="pitch", pause_ms=100, call=call, rt_ms=500, key=key, correct=int(ok), pitch_type=key, family="FB",
                         pocket="mid-mid", px=0.1, pz=2.5, sz_top=3.5, sz_bot=1.5, speed=90, stand="R", p_throws="R", release_frame=1, options="FF|SL|CH"))
    with open(f, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)
    pr = RP.profile(RP.load([str(f)]), "A")
    t = pr["pitch"]["summary"]
    assert t["chance_baseline"] == 0.333 and "d_prime" not in t and 0.6 < t["accuracy"] < 0.8
    assert pr["pitch"]["confusions"] and pr["pitch"]["confusions"][0][0] in ("FF", "SL", "CH")
    assert set(pr["pitch"]["by_pitch_type"]) == {"FF", "SL", "CH"}
    assert "What he named instead" in RP.render_html(pr)
