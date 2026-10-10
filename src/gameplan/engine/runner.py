"""Scheduled work and pack builds. `tick` is the whole scheduler: call it every minute; it runs whatever is due and records every run in job_runs. One instance of the service runs one scheduler.

  starters   every 3 hours: look up each team's next opponent starter and store it as SUGGESTED (or TBD). A person confirms; nothing is built from a suggestion.
  reconcile  every hour: store the findings from reconcile.findings.
  backup     once a day after 03:00 UTC: a verified copy of the database, last 14 kept.
Builds (`build_starter`) run only for a CONFIRMED starter, only through the prepare gates, and register packs only when every gate passes; a failed build changes nothing a hitter sees.
"""
from __future__ import annotations

import json
import logging
import pathlib
import threading
import traceback

from .. import next_starter as NS
from . import backup as BK
from . import db, identity, jobs, reconcile

log = logging.getLogger("engine.runner")
INTERVALS = dict(starters=3 * 3600, reconcile=3600, backup=24 * 3600)


def _last_run(c, name: str):
    r = c.execute("SELECT started_at FROM job_runs WHERE name=? AND ok=1 ORDER BY id DESC LIMIT 1", (name,)).fetchone()
    return r["started_at"] if r else None


def _record(c, name: str, fn):
    with db.tx(c):
        rid = c.execute("INSERT INTO job_runs(name, started_at) VALUES (?,?)", (name, db.now())).lastrowid
    try:
        detail = fn() or {}
        ok = 1
    except Exception as e:                       # a failed job is recorded and the service carries on
        detail, ok = dict(error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-600:]), 0
        log.exception("job %s failed", name)
    with db.tx(c):
        c.execute("UPDATE job_runs SET finished_at=?, ok=?, detail_json=? WHERE id=?", (db.now(), ok, json.dumps(detail, default=str), rid))
    return ok


def suggest_starters(c, resolver=NS.resolve) -> dict:
    out = dict(checked=0, suggested=0, tbd=0)
    for t in c.execute("SELECT * FROM teams WHERE active=1 AND mlb_team_id IS NOT NULL").fetchall():
        out["checked"] += 1
        try:
            r = resolver(t["mlb_team_id"], db.today(), sport_id=t["sport_id"] or 1)
        except Exception as e:                    # the schedule service being down must not stop anything else
            out.setdefault("errors", []).append(f"{t['name']}: {type(e).__name__}")
            continue
        if r["status"] == "no_game":
            continue
        have = c.execute("SELECT 1 FROM starters WHERE team_id=? AND game_date=? AND status='confirmed' AND (pitcher_id IS ? OR pitcher_id=?)", (t["id"], r["date"], r.get("pitcher_id"), r.get("pitcher_id"))).fetchone()
        if have:
            continue
        with db.tx(c):
            c.execute("UPDATE starters SET status='superseded' WHERE team_id=? AND game_date=? AND status IN ('suggested','tbd')", (t["id"], r["date"]))
            confirmed = c.execute("SELECT 1 FROM starters WHERE team_id=? AND game_date=? AND status='confirmed'", (t["id"], r["date"])).fetchone()
            if confirmed:
                continue
            c.execute("INSERT INTO starters(team_id, game_date, game_pk, pitcher_id, pitcher_name, status, source, checked_at, season) VALUES (?,?,?,?,?,?,?,?,?)",
                      (t["id"], r["date"], r.get("game_pk"), r.get("pitcher_id"), r.get("pitcher_name"), "suggested" if r["status"] == "confirmed" else "tbd", "schedule", r["checked_at"], r.get("season")))
        out["suggested" if r["status"] == "confirmed" else "tbd"] += 1
    return out


def tick(db_path: pathlib.Path, backup_dir: pathlib.Path, now: str | None = None, resolver=NS.resolve) -> list:
    """Run what is due. Returns the names that ran."""
    now = now or db.now()
    c = db.connect(db_path)
    ran = []
    try:
        for name, secs in INTERVALS.items():
            last = _last_run(c, name)
            if last is not None and last > db.plus(now, seconds=-secs):
                continue
            if name == "backup" and now[11:13] < "03" and last is not None:
                continue
            fn = dict(starters=lambda: suggest_starters(c, resolver), reconcile=lambda: dict(findings=reconcile.findings(c)),
                      backup=lambda: dict(file=str(BK.backup(db_path, backup_dir)), counts=BK.counts(db_path)))[name]
            _record(c, name, fn)
            ran.append(name)
    finally:
        c.close()
    return ran


def build_starter(db_path: pathlib.Path, data_dir: pathlib.Path, starter_id: int, prepare_fn=None) -> dict:
    """Build and register packs for one CONFIRMED starter. Runs the prepare gates; registers only when none FAILED. Returns {ok, gates, hashes}."""
    from .. import prepare as PR
    prepare_fn = prepare_fn or PR.prepare
    c = db.connect(db_path)
    try:
        st = c.execute("SELECT s.*, t.adapter, t.name team_name FROM starters s JOIN teams t ON t.id=s.team_id WHERE s.id=?", (starter_id,)).fetchone()
        if st is None:
            raise identity.EngineError("No such starter.", 404)
        if st["status"] != "confirmed":
            raise identity.EngineError("Only a confirmed starter can be built.", 409)
        if st["adapter"] not in ("mlb_video", "tracking_drawn") or not st["pitcher_id"]:
            raise identity.EngineError("This team has no pitch source for that starter. Practice packs are shown instead.", 409)
        work = pathlib.Path(data_dir) / "work" / str(starter_id)
        content = work / "content"
        work.mkdir(parents=True, exist_ok=True)
        rep = prepare_fn(None, st["game_date"], work, content, st["pitcher_id"], 4, 6, sim=(st["adapter"] == "tracking_drawn"))
        out = dict(ok=bool(rep.get("ok")), gates=rep.get("gates", []), hashes=[])
        if out["ok"] and rep.get("built"):
            keys = json.loads((work / "private_keys.json").read_text())
            out["hashes"] = jobs.register_queue(c, content, pathlib.Path(data_dir) / "content", st["team_id"], starter_id, st["adapter"], keys, gate_report=dict(gates=rep["gates"]))
            with db.tx(c):
                c.execute("UPDATE packs SET status='retired' WHERE team_id=? AND practice=0 AND status='active' AND (starter_id IS NULL OR starter_id<>?)", (st["team_id"], starter_id))
                db.audit(c, "system", None, "starter_built", dict(starter_id=starter_id, packs=len(out["hashes"])))
        else:
            with db.tx(c):
                db.audit(c, "system", None, "starter_build_failed", dict(starter_id=starter_id, failed=[g for g in out["gates"] if g.get("status") == "FAIL"][:5]))
        return out
    finally:
        c.close()


def start_background(db_path, data_dir, backup_dir, period: int = 60):
    stop = threading.Event()

    def loop():
        while not stop.wait(period):
            try:
                tick(db_path, backup_dir)
            except Exception:
                log.exception("scheduler tick failed")
    th = threading.Thread(target=loop, daemon=True, name="engine-scheduler")
    th.start()
    return stop
