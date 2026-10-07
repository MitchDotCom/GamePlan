"""Batch runner and evaluator for the low-home release detector (acceptance test: docs/LOWHOME_ACCEPTANCE.md).

  python -m gameplan.lowhome_batch run   <clip folder> --profile <profile.json> --out <out folder> [--workers N]
  python -m gameplan.lowhome_batch eval  <out folder> <labels.json> [--report report.md]
  python -m gameplan.lowhome_batch calibrate <clip folder> --out profile.json [--name NAME]

run: one JSON record and one audit strip per clip. Records already on disk are skipped, so an interrupted run resumes. A clip that raises an error is
recorded as an error and the rest continue. Every record carries its processing time.

labels.json: {"<clip stem>": {"claude": 456, "owner": 455}}  (any number of labelers, release frame each)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from . import lowhome_release as L

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".avi", ".mkv")


def _one(args):
    path, profile_json, out_dir, force = args
    out = pathlib.Path(out_dir)
    rec_path = out / f"{pathlib.Path(path).stem}.json"
    if rec_path.exists() and not force:
        return json.loads(rec_path.read_text())
    t = time.time()
    try:
        prof = L.CameraProfile.from_json(profile_json)
        rec = L.analyze(path, prof)
        if rec["status"] == "ok":
            L.audit_strip(path, rec, out / f"{pathlib.Path(path).stem}_audit.jpg")
    except Exception as e:  # one bad clip never stops the batch
        rec = dict(clip=pathlib.Path(path).name, status="error", reason=f"{type(e).__name__}: {str(e)[:160]}", checks={})
    rec["seconds"] = round(time.time() - t, 2)
    rec_path.write_text(json.dumps(rec))
    return rec


def run(folder: str, profile_path: str, out_dir: str, workers: int = 1, force: bool = False) -> list:
    clips = sorted(p for p in pathlib.Path(folder).iterdir() if p.suffix.lower() in VIDEO_EXT)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pj = pathlib.Path(profile_path).read_text()
    jobs = [(str(p), pj, str(out), force) for p in clips]
    if workers > 1:
        with ProcessPoolExecutor(workers) as ex:
            recs = list(ex.map(_one, jobs))
    else:
        recs = [_one(j) for j in jobs]
    ok = sum(r["status"] == "ok" for r in recs)
    secs = [r.get("seconds", 0) for r in recs]
    print(f"{len(recs)} clips: {ok} released, {len(recs) - ok} not (fail closed or error); median {np.median(secs):.1f} s per clip, max {max(secs):.1f} s")
    return recs


def evaluate(out_dir: str, labels_path: str) -> dict:
    """Acceptance metrics. Error = detector frame minus the mean of the labelers' frames."""
    labels = json.loads(pathlib.Path(labels_path).read_text())
    rows = []
    for f in sorted(pathlib.Path(out_dir).glob("*.json")):
        rec = json.loads(f.read_text())
        stem = f.stem
        lab = labels.get(stem)
        if lab is None:
            continue
        vals = [v for v in lab.values() if isinstance(v, (int, float))]
        if not vals:
            continue
        ambiguous = (max(vals) - min(vals)) > 1
        det = rec.get("release_frame") if rec["status"] == "ok" else None
        err = None if det is None else det - float(np.mean(vals))
        rows.append(dict(clip=stem, labels=vals, ambiguous=ambiguous, detected=det, status=rec["status"], reason=rec.get("reason"), error=err,
                         worst=None if det is None else max(abs(det - v) for v in vals)))
    scored = [r for r in rows if not r["ambiguous"]]
    found = [r for r in scored if r["detected"] is not None]
    n = len(scored)
    m = dict(n_clips=len(rows), n_ambiguous=len(rows) - n, n_scored=n, n_found=len(found),
             not_found_rate=(n - len(found)) / n if n else None,
             within1=sum(r["worst"] <= 1 for r in found) / n if n else None,
             within2=sum(r["worst"] <= 2 for r in found) / n if n else None,
             silent_error_rate=sum(r["worst"] > 3 for r in found) / n if n else None,
             mean_signed_error=float(np.mean([r["error"] for r in found])) if found else None)
    m["bars"] = dict(within1=m["within1"] is not None and m["within1"] >= 0.90, within2=m["within2"] is not None and m["within2"] >= 0.97,
                     mean_signed_error=m["mean_signed_error"] is not None and abs(m["mean_signed_error"]) <= 0.5,
                     not_found_rate=m["not_found_rate"] is not None and m["not_found_rate"] <= 0.10,
                     silent_error_rate=m["silent_error_rate"] is not None and m["silent_error_rate"] <= 0.02)
    return dict(metrics=m, rows=rows)


def report(res: dict) -> str:
    m, rows = res["metrics"], res["rows"]
    f = lambda x, p=False: "n/a" if x is None else (f"{x:.1%}" if p else f"{x:+.2f}")
    b = m["bars"]
    out = [f"# Low-home release detector, acceptance report", "",
           f"Clips with labels: {m['n_clips']} ({m['n_ambiguous']} ambiguous, excluded from rates); scored {m['n_scored']}; released {m['n_found']}.", "",
           "| Metric | Result | Bar | Met |", "|---|---|---|---|",
           f"| Within 1 frame | {f(m['within1'], True)} | at least 90% | {b['within1']} |",
           f"| Within 2 frames | {f(m['within2'], True)} | at least 97% | {b['within2']} |",
           f"| Mean signed error (frames) | {f(m['mean_signed_error'])} | within +/-0.5 | {b['mean_signed_error']} |",
           f"| Not released (fail closed) | {f(m['not_found_rate'], True)} | at most 10% | {b['not_found_rate']} |",
           f"| Silent errors (off by more than 3) | {f(m['silent_error_rate'], True)} | at most 2% | {b['silent_error_rate']} |", "",
           "| Clip | Labels | Detector | Error | Note |", "|---|---|---|---|---|"]
    for r in rows:
        note = "ambiguous labels" if r["ambiguous"] else (r["reason"] or "")
        out.append(f"| {r['clip']} | {r['labels']} | {r['detected'] if r['detected'] is not None else 'none'} | {f(r['error']) if r['error'] is not None else ''} | {note} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("folder"); r.add_argument("--profile", required=True); r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=1); r.add_argument("--force", action="store_true")
    e = sub.add_parser("eval"); e.add_argument("out"); e.add_argument("labels"); e.add_argument("--report", default=None)
    c = sub.add_parser("calibrate"); c.add_argument("folder"); c.add_argument("--out", required=True); c.add_argument("--name", default="camera")
    c.add_argument("--near", default=None, help="x,y rough point on the pitcher (only needed if something falls at the same place in every clip)"); c.add_argument("--overlay", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.folder, a.profile, a.out, a.workers, a.force)
    elif a.cmd == "eval":
        text = report(evaluate(a.out, a.labels))
        print(text)
        if a.report:
            pathlib.Path(a.report).write_text(text)
    else:
        clips = sorted(str(p) for p in pathlib.Path(a.folder).iterdir() if p.suffix.lower() in VIDEO_EXT)
        near = tuple(float(v) for v in a.near.split(",")) if a.near else None
        prof = L.calibrate(clips, name=a.name, near=near, overlay=a.overlay)
        pathlib.Path(a.out).write_text(prof.to_json())
        print(prof.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
