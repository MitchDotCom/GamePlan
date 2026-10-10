"""The playlist a hitter gets today. Deterministic: the same hitter, data and day give the same list (rule version recorded).

Rules (docs/ENGINE_PLAN.md 6.4):
  * only packs for his current team (or org-wide practice packs when his team has no confirmed starter with content, and the app says so), on the side(s) he bats;
  * kinds in order: next starter, edges, random, then the assessment pack when one is due (a form is taken only when every item is answered; a started form resumes with the items left; it never counts against the daily cap);
  * inside a training pack, pitches he has not answered yet come first, and among those pitches in his weakest locations come first (weak = at least MIN_CELL strike/ball answers and clearly below his own average);
  * the daily cap (set by the coach for his team) limits training pitches, dropping whole trailing items, never splitting a pitch's two questions.
"""
from __future__ import annotations

import json

from . import answers as A
from . import db, identity, packs, schedule

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


def assessment_state(c, player_id: int, pack_hash: str, n_items: int, every_days: int):
    """-> (offer: bool, remaining item ids or None).
    A form is TAKEN only when every item has an answer. A form he has started but not finished is offered again with only the items still to do, whatever the calendar says.
    A form he has not started is offered only if he has not finished some other form inside the last `every_days`."""
    mine = {r["item_id"] for r in c.execute(f"SELECT DISTINCT item_id FROM answers WHERE player_id=? AND pack_hash=? AND mode='assess' AND {A.LIVE}", (player_id, pack_hash))}
    if mine and len(mine) >= n_items:
        return False, None
    if mine:
        return True, mine
    done = c.execute(f"SELECT MAX(t) t FROM (SELECT a.pack_hash, MAX(a.server_ts) t FROM answers a WHERE a.player_id=? AND a.mode='assess' AND a.{A.LIVE} "
                     "GROUP BY a.pack_hash HAVING COUNT(DISTINCT a.item_id) >= (SELECT COUNT(*) FROM item_keys k WHERE k.pack_hash=a.pack_hash))", (player_id,)).fetchone()["t"]
    return (done is None or done < db.plus(db.now(), days=-every_days)), None


def order_items(items: list, seen: set, weak: list) -> list:
    return sorted(items, key=lambda it: (it["id"] in seen, (it.get("meta") or {}).get("pocket") not in weak, it["id"]))


def _games(entries) -> list:
    return [dict(date=e["game_date"], game_no=e["game_no"], starter=e["pitcher_name"], opponent=e["opponent"], comp=e["comp_note"] if e["content_kind"] == "comp" else None) for e in entries]


def compose(c, player, on: str | None = None, now_iso: str | None = None, record: bool = True) -> dict:
    """`on` pins the slate day (tests, replays); otherwise the day comes from the team's clock and any admin hold (schedule.slate_day).
    A pack tied to a starter is served only while that starter is on the hitter's slate; a pack tied to no starter is team-wide and always served."""
    now_iso = now_iso or db.now()
    asg = identity.current_assignment(c, player["id"], on or now_iso[:10])
    sd = None
    if on is None and asg is not None:
        sd = schedule.slate_day(c, asg["team_id"], now_iso)
        later = identity.current_assignment(c, player["id"], sd["date"])        # the team he will be on that day, so he prepares for his next opponent
        if later is not None and later["team_id"] != asg["team_id"]:
            asg = later
            sd = schedule.slate_day(c, asg["team_id"], now_iso)
    day = on or (sd["date"] if sd else now_iso[:10])
    out = dict(player=identity.player_card(c, player["id"]), date=day, rule_version=RULE_VERSION, packs=[], notes=[], settings=None, sides=[], slate=None, starter_names=[])
    if asg is None:
        out["notes"].append("You are not assigned to a team yet. Ask a coach.")
        return out
    st = settings(c, asg["team_id"])
    out["settings"] = st
    sides = ["L", "R"] if player["bats"] == "S" else [player["bats"]]
    out["sides"] = sides
    entries = schedule.entries_from(c, asg["team_id"], day)
    ids = [e["id"] for e in entries]
    out["starter_names"] = [e["pitcher_name"] for e in entries]
    out["slate"] = dict(day=day, source=sd["source"] if sd else "pinned", valid_until=sd["valid_until"] if sd else None, games=_games(entries))
    q = "SELECT p.*, COALESCE(s.game_no, 0) game_no FROM packs p LEFT JOIN starters s ON s.id=p.starter_id WHERE p.status='active' AND p.team_id=? AND p.practice=0 AND p.side IN (%s) AND (p.starter_id IS NULL%s)"
    rows = c.execute(q % (",".join("?" * len(sides)), (" OR p.starter_id IN (%s)" % ",".join("?" * len(ids))) if ids else ""), (asg["team_id"], *sides, *ids)).fetchall()
    if not [r for r in rows if r["kind"] != "assess"]:
        rows = rows + c.execute("SELECT *, 0 game_no FROM packs WHERE status='active' AND practice=1 AND side IN (%s)" % ",".join("?" * len(sides)), sides).fetchall()
        if [r for r in rows if r["practice"]]:
            if entries:
                out["notes"].append("Pitches for " + " and ".join(e["pitcher_name"] for e in entries) + " are not ready yet. Showing practice pitches, not your opponent.")
            else:
                out["notes"].append("No confirmed starter with pitches for your next opponent yet. Showing practice pitches, not your opponent.")
        else:
            out["notes"].append("Nothing is ready for your next opponent yet. Check again later.")
    weak = weak_pockets(c, player["id"])
    cap = st["daily_cap"]
    used = 0
    chosen = []
    for r in sorted(rows, key=lambda r: (KIND_ORDER.get(r["kind"], 9), r["game_no"], r["side"], r["hash"])):
        m = packs.player_manifest(r)
        if r["mode"] == "assess":
            offer, done_items = assessment_state(c, player["id"], r["hash"], len(m["items"]), st["assess_every_days"])
            if not offer:
                continue
            if done_items:
                m["items"] = [i for i in m["items"] if i["id"] not in done_items]
                m["resume"] = True
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
    if not record:
        return out
    with db.tx(c):
        c.execute("INSERT INTO playlists(player_id, play_date, side, pack_hashes_json, rule_version, created_at) VALUES (?,?,?,?,?,?) ON CONFLICT(player_id, play_date, side) DO UPDATE SET pack_hashes_json=excluded.pack_hashes_json, rule_version=excluded.rule_version",
                  (player["id"], day, side_key, json.dumps([m["id"] for m in chosen]), RULE_VERSION, db.now()))
    return out
