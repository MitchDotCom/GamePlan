"""Jobs the engine runs on content: registering built packs, confirming starters, and (separately) the nightly checks. Packs come from gameplan.prepare / app_content and are registered immutably."""
from __future__ import annotations

import json
import pathlib

from . import db, identity, packs, schedule

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


def confirm_starter(c, team_id: int, game_date: str, pitcher_id: int, pitcher_name: str, staff_id: int | None, game_pk: int | None = None, source: str = "staff", season: int | None = None,
                    game_no: int = 1, opponent: str | None = None) -> int:
    """A person says who the opposing starter is for one game. Earlier rows for the same team, date and game number are superseded, never deleted. Saving the same starter again changes nothing."""
    r = schedule.set_entry(c, team_id, game_date, pitcher_name, pitcher_id, opponent, staff_id, game_no, source)
    if game_pk is not None or season is not None:
        with db.tx(c):
            c.execute("UPDATE starters SET game_pk=COALESCE(?, game_pk), season=COALESCE(?, season) WHERE id=?", (game_pk, season, r["id"]))
    return r["id"]
