"""Tests for the low-home release detector on synthetic video (no org footage needed), plus a regression test on the development clips when present."""
import json
import os
import pathlib

import cv2
import numpy as np
import pytest

from gameplan import lowhome_release as L
from gameplan import lowhome_batch as B

FPS = 60


def synth(path, release, size=(1280, 720), n=190, ball=True, decoy_at=None, decoy_x=0.30, occlude=(7, 8), seed=0, pitcher_x=0.5):
    """A fixed camera behind the plate: green field, dark net lattice, a still pitcher who winds up and throws, a white ball that falls after release,
    static white plate and lines, noise. release = frame the ball first moves on its straight fall."""
    rng = np.random.default_rng(seed)
    W, H = size
    s = W / 1280.0
    bg = np.full((H, W, 3), (70, 140, 80), np.uint8)
    cv2.rectangle(bg, (0, int(H * .78)), (W, H), (60, 100, 150), -1)
    cv2.fillPoly(bg, [np.array([(int(560 * s), int(690 * s)), (int(720 * s), int(690 * s)), (int(700 * s), int(715 * s)), (int(580 * s), int(715 * s))])], (255, 255, 255))
    cv2.line(bg, (0, int(660 * s)), (W, int(660 * s)), (255, 255, 255), max(1, int(3 * s)))
    step = max(8, int(40 * s))
    for x in range(0, W, step):
        cv2.line(bg, (x, 0), (x, H), (30, 40, 30), 1)
    for y in range(0, H, step):
        cv2.line(bg, (0, y), (W, y), (30, 40, 30), 1)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    px = int(W * pitcher_x)
    by = int(95 * s)
    for f in range(n):
        im = bg.copy()
        k = f - (release - 14)
        shift = k if 0 < k < 20 else 0
        cv2.rectangle(im, (px - int(22 * s) + shift, by + int(25 * s)), (px + int(22 * s) + shift, by + int(165 * s)), (140, 130, 120), -1)
        cv2.circle(im, (px + shift, by + int(10 * s)), int(14 * s), (120, 110, 100), -1)
        if 0 <= k <= 20:
            ang = np.deg2rad(-100 + 12 * k)
            cv2.line(im, (px, by + int(40 * s)), (px + int(60 * s * np.cos(ang)), by + int(40 * s + 60 * s * np.sin(ang))), (60, 60, 60), max(2, int(10 * s)))
            cv2.circle(im, (px - int(30 * s), by + int(60 * s)), int(25 * s), (110, 100, 90), -1)
        if ball and f >= release:
            j = f - release
            if j not in range(occlude[0], occlude[1] + 1):       # the net pole hides the ball for a couple of frames
                y = by + int(30 * s) + (7.2 * j + 0.05 * j * j) * s
                cv2.circle(im, (int(px - 70 * s + 0.4 * j * s), int(y)), max(2, int(5 * s)), (255, 255, 255), -1)
        if decoy_at is not None and decoy_at <= f < decoy_at + 12:   # another white thing falling somewhere else, long before the pitch
            cv2.circle(im, (int(W * decoy_x), int((110 + 8 * (f - decoy_at)) * s)), max(2, int(5 * s)), (255, 255, 255), -1)
        noise = rng.integers(-3, 4, im.shape, dtype=np.int16)
        vw.write(np.clip(im.astype(np.int16) + noise, 0, 255).astype(np.uint8))
    vw.release()
    return path


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    d = tmp_path_factory.mktemp("full")
    rel = [140, 148, 144]
    clips = [str(synth(d / f"c{i}.avi", r, seed=i, decoy_at=20 + 5 * i, decoy_x=0.15 + 0.12 * i)) for i, r in enumerate(rel)]   # debris falls somewhere different in each clip
    return clips, rel, L.calibrate(clips, name="synthetic")


def test_calibration_finds_scale_and_place(full):
    clips, rel, prof = full
    assert prof.scale == 1.0
    x0, y0, x1, y1 = prof.pitcher_box
    assert x0 < 640 < x1 and y0 < 120 < y1                  # the pitcher stands inside the learned box


def test_release_frame_exact_on_synthetic(full):
    clips, rel, prof = full
    for c, r in zip(clips, rel):
        rec = L.analyze(c, prof)
        assert rec["status"] == "ok", rec["reason"]
        assert abs(rec["release_frame"] - r) <= 1               # net-hidden frames and noise included


def test_half_size_picture_scales(tmp_path):
    rel = [130, 138, 134]
    clips = [str(synth(tmp_path / f"h{i}.avi", r, size=(640, 360), seed=10 + i, decoy_at=15 + 4 * i, decoy_x=0.18 + 0.1 * i)) for i, r in enumerate(rel)]
    prof = L.calibrate(clips, name="half")
    assert prof.scale == 0.5
    for c, r in zip(clips, rel):
        rec = L.analyze(c, prof)
        assert rec["status"] == "ok", rec["reason"]
        assert abs(rec["release_frame"] - r) <= 1


def test_decoy_in_the_same_place_every_clip_needs_the_hint(tmp_path):
    rel = [140, 148, 144]
    clips = [str(synth(tmp_path / f"d{i}.avi", r, seed=20 + i, decoy_at=20 + 5 * i, decoy_x=0.30)) for i, r in enumerate(rel)]   # same decoy spot in every clip
    prof = L.calibrate(clips, name="hinted", near=(570, 125), overlay=str(tmp_path / "overlay.jpg"))      # one rough point on the pitcher, once per camera
    x0, y0, x1, y1 = prof.pitcher_box
    assert x0 < 640 < x1 and (tmp_path / "overlay.jpg").exists()
    for c, r in zip(clips, rel):
        rec = L.analyze(c, prof)
        assert rec["status"] == "ok" and abs(rec["release_frame"] - r) <= 1


def test_calibration_refuses_when_clips_do_not_agree(tmp_path):
    clips = [str(synth(tmp_path / f"n{i}.avi", 140, ball=False, seed=30 + i, decoy_at=20, decoy_x=0.2 + 0.2 * i)) for i in range(3)]
    with pytest.raises(ValueError):
        L.calibrate(clips, name="nothing")


def test_fails_closed_without_a_ball(full, tmp_path):
    clips, rel, prof = full
    c = str(synth(tmp_path / "noball.avi", 144, ball=False, seed=5))
    rec = L.analyze(c, prof)
    assert rec["status"] == "fail" and rec["reason"]
    assert L.find_release(c, prof) is None


def test_frame_size_mismatch_fails_closed(full, tmp_path):
    clips, rel, prof = full
    c = str(synth(tmp_path / "small.avi", 130, size=(640, 360), seed=6))
    rec = L.analyze(c, prof)
    assert rec["status"] == "fail" and "frame size" in rec["reason"]


def test_two_balls_at_once_is_ambiguous():
    t1 = [(f, (500.0, 100.0 + 7 * (f - 100), 40)) for f in range(100, 108)]
    t2 = [(f, (800.0, 160.0 + 7 * (f - 100), 40)) for f in range(100, 108)]
    assert L.competes(t1, t2, 1.0)


def test_subtracks_of_one_ball_and_non_overlapping_tracks_do_not_compete():
    t1 = [(f, (500.0, 100.0 + 7 * (f - 100), 40)) for f in range(100, 108)]
    t1b = [(f, (503.0, 100.0 + 7 * (f - 100) + 2, 40)) for f in range(102, 108)]
    later = [(f, (800.0, 300.0 + 7 * (f - 130), 40)) for f in range(130, 138)]
    assert not L.competes(t1, t1b, 1.0) and not L.competes(t1, later, 1.0)


def test_batch_resumes_and_reports(full, tmp_path):
    clips, rel, prof = full
    folder = tmp_path / "in"
    folder.mkdir()
    for c in clips:
        os.symlink(c, folder / pathlib.Path(c).name)
    (folder / "broken.avi").write_bytes(b"not a video")
    pj = tmp_path / "p.json"
    pj.write_text(prof.to_json())
    out = tmp_path / "out"
    recs = B.run(str(folder), str(pj), str(out))
    assert len(recs) == 4 and sum(r["status"] == "ok" for r in recs) == 3
    assert [r for r in recs if r["clip"] == "broken.avi"][0]["status"] in ("error", "fail")   # a bad clip does not stop the rest
    t0 = {r["clip"]: r["seconds"] for r in recs}
    again = B.run(str(folder), str(pj), str(out))                       # resumes from the saved records
    assert {r["clip"]: r["seconds"] for r in again} == t0
    assert (out / "c0_audit.jpg").exists()
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({f"c{i}": {"a": r, "b": r} for i, r in enumerate(rel)}))
    res = B.evaluate(str(out), str(labels))
    assert res["metrics"]["n_scored"] == 3 and res["metrics"]["within1"] == 1.0
    assert "Within 1 frame" in B.report(res)


def test_evaluate_marks_labeler_disagreement_ambiguous(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "x.json").write_text(json.dumps(dict(clip="x.mp4", status="ok", release_frame=100, checks={})))
    (out / "y.json").write_text(json.dumps(dict(clip="y.mp4", status="fail", reason="no ball", checks={})))
    lab = tmp_path / "l.json"
    lab.write_text(json.dumps({"x": {"a": 100, "b": 104}, "y": {"a": 50, "b": 50}}))
    res = B.evaluate(str(out), str(lab))["metrics"]
    assert res["n_ambiguous"] == 1 and res["not_found_rate"] == 1.0


DEV = pathlib.Path(os.environ.get("LOWHOME_DEV_CLIPS", "/tmp/claude-0/lowhome"))


@pytest.mark.skipif(not (DEV / "a1016406-2443D.mp4").exists(), reason="development clips not present")
def test_development_clips_match_hand_labels(tmp_path):
    clips = sorted(str(p) for p in DEV.glob("*.mp4"))
    prof = L.calibrate(clips, name="dev")
    labels = json.loads((pathlib.Path(__file__).parent / "data" / "lowhome_dev_labels.json").read_text())
    for c in clips:
        stem = pathlib.Path(c).stem
        rec = L.analyze(c, prof)
        assert rec["status"] == "ok", (stem, rec["reason"])
        assert rec["release_frame"] == labels[stem]["claude"]
