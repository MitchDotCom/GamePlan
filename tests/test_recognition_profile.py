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
        key = "GO" if rng.random() < 0.5 else "NO-GO"
        acc = weak[1] if pk == weak[0] else base
        ok = rng.random() < acc
        call = key if ok else ("NO-GO" if key == "GO" else "GO")
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
    assert "Zone recognition" in page and "low-away" in page
    assert RP.edge_bucket(dict(px=1.2, pz=2.5, sz_top=3.5, sz_bot=1.5)).startswith("outside")
    assert RP.edge_bucket(dict(px=0.0, pz=2.5, sz_top=3.5, sz_bot=1.5)).startswith("inside, deeper")
