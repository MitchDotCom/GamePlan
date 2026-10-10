"""Seed a demo organization for trying the engine: teams, a few hitters, a staff login, and packs from a content folder built by gameplan.prepare / app_content.

  python -m gameplan.engine.seed --data ./engine_data --secret ... --content <dir with queue_L.json, queue_R.json and pack folders> [--private-keys <file>] [--practice]

Prints one claim link per hitter and a coach and admin token (shown once). Use --base-url to print full links.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from . import db, identity, jobs


def seed(data_dir: pathlib.Path, secret: str, content: pathlib.Path | None, private_keys: pathlib.Path | None, base_url: str = "", drawn_content: pathlib.Path | None = None, drawn_private_keys: pathlib.Path | None = None) -> dict:
    data_dir = pathlib.Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    c = db.connect(data_dir / "engine.db")
    db.migrate(c)
    out = dict(claims={}, staff={})
    if c.execute("SELECT COUNT(*) n FROM teams").fetchone()["n"]:
        raise SystemExit("This database already has teams; refusing to seed it again.")
    t_vis = identity.add_team(c, "Visalia Rawhide", "Single-A", 516, 14, "none")
    t_ari = identity.add_team(c, "Arizona Diamondbacks (demo)", "MLB", 109, 1, "mlb_video")
    roster = [("Demo Hitter One", "L", t_vis, "DEMO-1"), ("Demo Hitter Two", "R", t_vis, "DEMO-2"), ("Demo Switch Hitter", "S", t_ari, "DEMO-3"), ("Demo Hitter Four", "R", t_ari, "DEMO-4")]
    pids = {}
    for name, bats, team, oid in roster:
        pids[name] = identity.add_player(c, name, bats, team, oid)
    _, admin = identity.create_staff(c, secret, "Admin", "admin")
    _, coach = identity.create_staff(c, secret, "Demo Coach", "coach", [t_vis, t_ari])
    out["staff"] = dict(admin=admin, coach=coach)
    if content:
        keys = json.loads(pathlib.Path(private_keys).read_text()) if private_keys else None
        hashes = jobs.register_queue(c, content, data_dir / "content", t_ari, None, "mlb_video", keys, practice=False)
        hashes += jobs.register_queue(c, content, data_dir / "content", None, None, "mlb_video", keys, practice=True)
        out["packs"] = len(set(hashes))
    if drawn_content:
        dkeys = json.loads(pathlib.Path(drawn_private_keys).read_text()) if drawn_private_keys else None
        dh = jobs.register_queue(c, drawn_content, data_dir / "content", None, None, "tracking_drawn", dkeys, practice=True)
        out["practice_packs"] = len(set(dh))
    c.execute("UPDATE level_settings SET pause_ms=200, view='low_home' WHERE team_id=?", (t_vis,))
    c.execute("UPDATE level_settings SET pause_ms=150, view='hitter_eye' WHERE team_id=?", (t_ari,))
    for name, pid in pids.items():
        out["claims"][name] = base_url.rstrip("/") + "/c/" + identity.create_claim(c, secret, pid)
    c.close()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--secret", required=True)
    ap.add_argument("--content", default=None)
    ap.add_argument("--private-keys", default=None)
    ap.add_argument("--base-url", default="")
    ap.add_argument("--drawn-content", default=None, help="drawn-from-tracking packs, registered as practice packs for teams with no opponent data")
    ap.add_argument("--drawn-private-keys", default=None)
    a = ap.parse_args(argv)
    P = lambda x: pathlib.Path(x) if x else None
    r = seed(pathlib.Path(a.data), a.secret, P(a.content), P(a.private_keys), a.base_url, P(a.drawn_content), P(a.drawn_private_keys))
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
