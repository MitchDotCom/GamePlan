"""Coach numbers from the engine database: the same board code as gameplan.season_ledger, fed from the live (not voided) answers. Everything here is read-only and rebuilt from the raw answer log."""
from __future__ import annotations

from .. import season_ledger as SL
from . import answers as A
from . import db

LEVEL_RANK = {"DSL": 0, "ACL": 1, "Rookie": 1, "Single-A": 2, "A": 2, "High-A": 3, "Double-A": 4, "Triple-A": 5, "AAA": 5, "MLB": 6}


def rows(c, team_ids: list | None = None, player_id: int | None = None) -> list:
    """Live answers as ledger rows. `player` is the player's name, with his id added when two players share a name, so two hitters are never merged."""
    q = (f"SELECT a.*, p.name FROM answers a JOIN players p ON p.id=a.player_id WHERE a.{A.LIVE}")
    args: list = []
    if player_id is not None:
        q += " AND a.player_id=?"
        args.append(player_id)
    if team_ids is not None:
        if not team_ids:
            return []
        q += " AND a.team_id IN (%s)" % ",".join("?" * len(team_ids))
        args += team_ids
    dup = {r["name"] for r in c.execute("SELECT name FROM players GROUP BY name HAVING COUNT(*)>1")}
    out = []
    for r in c.execute(q + " ORDER BY a.server_ts", args):
        d = dict(r)
        d["player"] = f"{r['name']} (#{r['player_id']})" if r["name"] in dup else r["name"]
        d["pid"] = r["player_id"]
        d["clip"] = r["item_id"]
        d["pack"] = r["pack_hash"]
        d["ts"] = r["server_ts"]
        out.append(SL.normalize(d))
    return out


def boards(c, team_ids: list | None, mode: str = "assess", min_n: int = SL.MIN_N) -> dict:
    return SL.boards(rows(c, team_ids), mode, min_n)


def player_view(c, player_id: int) -> dict:
    """Per camera class and mode: his ledger (pocket maps, edge, pitch-type recall, confusions, trend). Peer adjustment uses everyone on his teams so a hard pack is not held against him."""
    teams = [r["team_id"] for r in c.execute("SELECT DISTINCT team_id FROM assignments WHERE player_id=?", (player_id,))]
    allr = rows(c, teams)
    me = [r for r in allr if r["pid"] == player_id]
    out = {}
    for mode in ("assess", "train"):
        for cc in sorted({r["camera_class"] for r in me if r["mode"] == mode}):
            rs = [r for r in allr if r["mode"] == mode and r["camera_class"] == cc]
            exp = SL.peer_expectation(rs)
            out[(mode, cc)] = SL.player_ledger([r for r in rs if r["pid"] == player_id], exp)
    return out
