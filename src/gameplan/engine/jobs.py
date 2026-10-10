"""Jobs the engine runs on content: registering built packs, confirming starters, and (separately) the nightly checks. Packs come from gameplan.prepare / app_content and are registered immutably."""
from __future__ import annotations

import json
import pathlib

from . import db, identity, packs

KINDS = {"starter": "starter", "edges": "edges", "random": "random", "assess": "assess"}


def register_queue(c, content_dir: pathlib.Path, content_root: pathlib.Path, team_id: int | None, starter_id: int | None, adapter: str, private_keys: dict | None = None,
                   gate_report: dict | None = None, practice: bool = False) -> list:
    """Register every pack in queue_L.json and queue_R.json under content_dir. Returns the pack hashes. Safe to run again: identical packs keep their hash."""
    out = []
    for side in ("L", "R"):
        f = pathlib.Path(content_dir) / f"queue_{side}.json"
        if not f.exists():
            continue
        for pk in json.loads(f.read_text())["packs"]:
            kind = KINDS.get(pk["id"].split("_")[0], "random")
            out.append(packs.register(c, pk, kind, side, adapter, content_root, content_dir, team_id, starter_id, private_keys, gate_report, practice))
    return out


def confirm_starter(c, team_id: int, game_date: str, pitcher_id: int, pitcher_name: str, staff_id: int | None, game_pk: int | None = None, source: str = "staff", season: int | None = None) -> int:
    """A person says who the opposing starter is. Earlier confirmed rows for the same team and date are superseded, never deleted."""
    if not pitcher_name or not str(pitcher_name).strip():
        raise identity.EngineError("A starter needs a name.")
    with db.tx(c):
        c.execute("UPDATE starters SET status='superseded' WHERE team_id=? AND game_date=? AND status IN ('confirmed','suggested','tbd')", (team_id, game_date))
        cur = c.execute("INSERT INTO starters(team_id, game_date, game_pk, pitcher_id, pitcher_name, status, source, checked_at, confirmed_by, confirmed_at, season) VALUES (?,?,?,?,?,'confirmed',?,?,?,?,?)",
                        (team_id, game_date, game_pk, pitcher_id, pitcher_name.strip()[:120], source, db.now(), staff_id, db.now(), season or int(game_date[:4])))
        db.audit(c, "staff", staff_id, "starter_confirmed", dict(team_id=team_id, game_date=game_date, pitcher_id=pitcher_id, pitcher_name=pitcher_name))
    return cur.lastrowid
