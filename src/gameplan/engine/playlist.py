"""The playlist a hitter gets today. Deterministic: the same hitter, data and day give the same list (rule version recorded).

Rules (docs/ENGINE_PLAN.md 6.4):
  * only packs for his current team (or org-wide practice packs when his team has no confirmed starter with content, and the app says so), on the side(s) he bats;
  * kinds in order: next starter, edges, random, then the assessment pack when one is due and not yet taken (an assessment pack is whole or absent; it never counts against the daily cap);
  * inside a training pack, pitches he has not answered yet come first, and among those pitches in his weakest locations come first (weak = at least MIN_CELL strike/ball answers and clearly below his own average);
  * the daily cap (set by the coach for his team) limits training pitches, dropping whole trailing items, never splitting a pitch's two questions.
"""
from __future__ import annotations

import json

from . import answers as A
from . import db, identity, packs

RULE_VERSION = "v1"
MIN_CELL = 8
KIND_ORDER = {"starter": 0, "edges": 1, "random": 2, "assess": 3}


def settings(c, team_id: int) -> dict:
    r = c.execute("SELECT * FROM level_settings WHERE team_id=?", (team_id,)).fetchone()
    return dict(pause_ms=r["pause_ms"], view=r["view"], daily_cap=r["daily_cap"], ask=r["ask"], reveal=bool(r["reveal"]), assess_every_days=r["assess_every_days"]) if r else dict(pause_ms=150, view="hitter_eye", daily_cap=30, ask="both", reveal=True, assess_every_days=28)


def weak_pockets(c, player_id: int, k: int = 2) -> list:
    rows = c.execute(f"SELECT pocket, COUNT(*) n, SUM(correct) s FROM answers WHERE player_id=? AND task='zone' AND correct IS NOT NULL AND pocket IS NOT NULL AND {A.LIVE} GROUP BY pocket", (player_id,)).fetchall()
    tot = sum(r["n"] for r in rows)
    if tot < 3 * MIN_CELL:
        return []
    overall = sum(r["s"] for r in rows) / tot
    weak = [(r["s"] / r["n"], r["pocket"]) for r in rows if r["n"] >= MIN_CELL and r["s"] / r["n"] < overall - 0.05]
    return [p for _, p in sorted(weak)[:k]]


def seen_items(c, player_id: int, pack_hash: str) -> set:
    return {r["item_id"] for r in c.execute(f"SELECT DISTINCT item_id FROM answers WHERE player_id=? AND pack_hash=? AND {A.LIVE}", (player_id, pack_hash))}


def assessment_due(c, player_id: int, pack_hash: str, every_days: int) -> bool:
    if c.execute(f"SELECT 1 FROM answers WHERE player_id=? AND pack_hash=? AND mode='assess' AND {A.LIVE} LIMIT 1", (player_id, pack_hash)).fetchone():
        return False                                                 # already took this exact form
    last = c.execute(f"SELECT MAX(server_ts) t FROM answers WHERE player_id=? AND mode='assess' AND {A.LIVE}", (player_id,)).fetchone()["t"]
    return last is None or last < db.plus(db.now(), days=-every_days)


def order_items(items: list, seen: set, weak: list) -> list:
    return sorted(items, key=lambda it: (it["id"] in seen, (it.get("meta") or {}).get("pocket") not in weak, it["id"]))


def compose(c, player, on: str | None = None) -> dict:
    on = on or db.today()
    asg = identity.current_assignment(c, player["id"], on)
    out = dict(player=identity.player_card(c, player["id"]), date=on, rule_version=RULE_VERSION, packs=[], notes=[], settings=None, sides=[])
    if asg is None:
        out["notes"].append("You are not assigned to a team yet. Ask a coach.")
        return out
    st = settings(c, asg["team_id"])
    out["settings"] = st
    sides = ["L", "R"] if player["bats"] == "S" else [player["bats"]]
    out["sides"] = sides
    rows = c.execute("SELECT * FROM packs WHERE status='active' AND team_id=? AND side IN (%s) AND practice=0" % ",".join("?" * len(sides)), (asg["team_id"], *sides)).fetchall()
    if not [r for r in rows if r["kind"] != "assess"]:
        rows = rows + c.execute("SELECT * FROM packs WHERE status='active' AND practice=1 AND side IN (%s)" % ",".join("?" * len(sides)), sides).fetchall()
        if [r for r in rows if r["practice"]]:
            out["notes"].append("No confirmed starter with pitches for your next opponent yet. Showing practice pitches, not your opponent.")
        else:
            out["notes"].append("Nothing is ready for your next opponent yet. Check again later.")
    weak = weak_pockets(c, player["id"])
    cap = st["daily_cap"]
    used = 0
    chosen = []
    for r in sorted(rows, key=lambda r: (KIND_ORDER.get(r["kind"], 9), r["side"], r["hash"])):
        m = packs.player_manifest(r)
        if r["mode"] == "assess":
            if not assessment_due(c, player["id"], r["hash"], st["assess_every_days"]):
                continue
            m["assess_due"] = True
        else:
            items = order_items(m["items"], seen_items(c, player["id"], r["hash"]), weak)
            room = max(0, cap - used)
            if room <= 0:
                continue
            m["items"] = items[:room]
            used += len(m["items"])
        m["practice"] = bool(r["practice"])
        m["camera"] = r["camera"]
        chosen.append(m)
    out["packs"] = chosen
    out["weak_pockets"] = weak
    side_key = ",".join(sides)
    with db.tx(c):
        c.execute("INSERT INTO playlists(player_id, play_date, side, pack_hashes_json, rule_version, created_at) VALUES (?,?,?,?,?,?) ON CONFLICT(player_id, play_date, side) DO UPDATE SET pack_hashes_json=excluded.pack_hashes_json, rule_version=excluded.rule_version",
                  (player["id"], on, side_key, json.dumps([m["id"] for m in chosen]), RULE_VERSION, db.now()))
    return out
