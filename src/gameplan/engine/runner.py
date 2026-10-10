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
from . import offsite as OFF
from . import db, identity, jobs, reconcile

log = logging.getLogger("engine.runner")
INTERVALS = dict(starters=3 * 3600, reconcile=3600, backup=6 * 3600, offsite=6 * 3600)          # a disk lost at the worst moment costs at most six hours of answers (and the phones resend those)


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
            r = resolver(t["mlb_team_id"], db.local_today(), sport_id=t["sport_id"] or 1)
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
                      backup=lambda: dict(file=str(BK.backup(db_path, backup_dir)), counts=BK.counts(db_path)), offsite=lambda: OFF.push(backup_dir))[name]
            _record(c, name, fn)
            ran.append(name)
    finally:
        c.close()
    return ran


def _set_build(c, starter_id: int, state: str, detail: str = "") -> None:
    with db.tx(c):
        c.execute("UPDATE starters SET build_state=?, build_detail=?, build_at=? WHERE id=?", (state, detail[:400], db.now(), starter_id))


def _failed_gates(gates: list) -> str:
    return "; ".join(f"{g['gate']} {g.get('side') or ''}: {str(g.get('detail') or '')[:90]}".replace("  ", " ").strip() for g in gates if g.get("status") == "FAIL")[:380]


def _label_comp(content: pathlib.Path, starter_name: str, comp_name: str) -> None:
    """Pitches from a stand-in pitcher must never read as the real starter's. Retitle the packs built from him before they are hashed and registered."""
    for side in ("L", "R"):
        f = pathlib.Path(content) / f"queue_{side}.json"
        if not f.exists():
            continue
        q = json.loads(f.read_text())
        for pk in q["packs"]:
            if pk["id"].startswith(("starter_", "edges_")):
                pk["title"] = f"Comp for {starter_name}: {comp_name}"
                pk["subtitle"] = f"Not {starter_name}'s own video. {comp_name} has a similar arm and arsenal. " + (pk.get("subtitle") or "")
        f.write_text(json.dumps(q))


def build_starter(db_path: pathlib.Path, data_dir: pathlib.Path, starter_id: int, prepare_fn=None) -> dict:
    """Build and register packs for one CONFIRMED game. Runs the prepare gates; registers only when none FAILED. Returns {ok, gates, hashes}.
    Only this game's earlier packs are retired when a rebuild replaces them: the other days of the week keep theirs."""
    from .. import prepare as PR
    prepare_fn = prepare_fn or PR.prepare
    c = db.connect(db_path)
    try:
        st = c.execute("SELECT s.*, t.adapter, t.name team_name FROM starters s JOIN teams t ON t.id=s.team_id WHERE s.id=?", (starter_id,)).fetchone()
        if st is None:
            raise identity.EngineError("No such starter.", 404)
        if st["status"] != "confirmed":
            raise identity.EngineError("Only a confirmed starter can be built.", 409)
        source_id = st["content_pitcher_id"] or st["pitcher_id"]
        comp = st["content_kind"] == "comp"
        adapter = "mlb_video" if comp else st["adapter"]                  # a comp is an MLB pitcher: his real video is cut, whatever the affiliate's own source
        if adapter not in ("mlb_video", "tracking_drawn") or not source_id:
            _set_build(c, starter_id, "", "")
            raise identity.EngineError("This team has no pitch source for that starter. Practice packs are shown instead.", 409)
        _set_build(c, starter_id, "building")
        work = pathlib.Path(data_dir) / "work" / str(starter_id)
        content = work / "content"
        work.mkdir(parents=True, exist_ok=True)
        try:
            rep = prepare_fn(None, st["game_date"], work, content, source_id, 4, 6, sim=(adapter == "tracking_drawn"))
        except Exception as e:
            _set_build(c, starter_id, "failed", f"{type(e).__name__}: {str(e)[:200]}")
            return dict(ok=False, gates=[], hashes=[], error=type(e).__name__)
        out = dict(ok=bool(rep.get("ok")), gates=rep.get("gates", []), hashes=[])
        if out["ok"] and rep.get("built"):
            if comp and st["comp_note"]:
                _label_comp(content, st["pitcher_name"], st["comp_note"])
            keys = json.loads((work / "private_keys.json").read_text())
            out["hashes"] = jobs.register_queue(c, content, pathlib.Path(data_dir) / "content", st["team_id"], starter_id, adapter, keys, gate_report=dict(gates=rep["gates"]))
            with db.tx(c):
                mark = ",".join("?" * len(set(out["hashes"])))
                c.execute(f"UPDATE packs SET status='retired' WHERE starter_id=? AND practice=0 AND status='active' AND hash NOT IN ({mark})", (starter_id, *set(out["hashes"])))
                db.audit(c, "system", None, "starter_built", dict(starter_id=starter_id, packs=len(out["hashes"])))
            _set_build(c, starter_id, "ready", f"{len(set(out['hashes']))} packs" + (" (comp)" if st["content_kind"] == "comp" else ""))
        else:
            fails = [g for g in out["gates"] if g.get("status") == "FAIL"]
            no_pitches = any(g.get("gate") in ("history", "build") for g in fails)
            with db.tx(c):
                db.audit(c, "system", None, "starter_build_failed", dict(starter_id=starter_id, failed=fails[:5]))
            _set_build(c, starter_id, "no_video" if no_pitches else "failed", _failed_gates(out["gates"]) or "build did not complete")
        return out
    finally:
        c.close()


def build_queued(db_path: pathlib.Path, data_dir: pathlib.Path, prepare_fn=None, limit: int = 1, now: str | None = None) -> list:
    """Build the soonest queued games, one at a time. A build left 'building' by a restart is marked failed so it shows and can be retried, never silently stuck."""
    now = now or db.now()
    c = db.connect(db_path)
    try:
        with db.tx(c):
            c.execute("UPDATE starters SET build_state='failed', build_detail='interrupted by a restart: retry' WHERE build_state='building' AND build_at<?", (db.plus(now, minutes=-30),))
        ids = [r["id"] for r in c.execute("SELECT id FROM starters WHERE status='confirmed' AND build_state='queued' AND game_date>=? ORDER BY game_date, game_no, id LIMIT ?", (db.plus(now, days=-1)[:10], limit))]
    finally:
        c.close()
    done = []
    for sid in ids:
        try:
            build_starter(db_path, data_dir, sid, prepare_fn)
        except identity.EngineError:
            pass
        done.append(sid)
    return done


def start_background(db_path, data_dir, backup_dir, period: int = 60):
    stop = threading.Event()

    def build_loop():
        while not stop.wait(20):
            try:
                build_queued(db_path, data_dir)
            except Exception:
                log.exception("build loop failed")
    threading.Thread(target=build_loop, daemon=True, name="engine-builder").start()

    def loop():
        while not stop.wait(period):
            try:
                tick(db_path, backup_dir)
            except Exception:
                log.exception("scheduler tick failed")
    th = threading.Thread(target=loop, daemon=True, name="engine-scheduler")
    th.start()
    return stop
