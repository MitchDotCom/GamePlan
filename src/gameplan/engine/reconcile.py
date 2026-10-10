"""Does the server hold what the phones say they sent, and who has not been heard from? Run hourly and shown on the staff attention list.

Findings (each names a player and what to do):
  possible_loss     the phone's latest heartbeat says it sent more answers than the server holds for him (stored + voided are both kept, so fewer than sent means rows went missing)
  stale_unsent      the phone reported unsent answers more than UNSENT_HOURS ago and nothing newer has arrived
  silent            a hitter set up more than SILENT_DAYS ago with no answer in SILENT_DAYS (opening the app without answering still counts as silent)
  never_claimed     a rostered hitter with no credential and a claim link older than 3 days (or none issued)
  rejected          the phone reports answers the server refused (a phone or content problem to look at)
"""
from __future__ import annotations

import json

from . import answers as A
from . import db

UNSENT_HOURS = 24
SILENT_DAYS = 7


def findings(c, team_ids: list | None = None) -> list:
    out = []
    q = "SELECT p.id, p.name FROM players p WHERE p.active=1"
    args: list = []
    if team_ids is not None:
        if not team_ids:
            return []
        q += " AND EXISTS (SELECT 1 FROM assignments a WHERE a.player_id=p.id AND a.end_date IS NULL AND a.team_id IN (%s))" % ",".join("?" * len(team_ids))
        args = list(team_ids)
    now = db.now()
    for p in c.execute(q, args).fetchall():
        pid = p["id"]
        creds = c.execute("SELECT COUNT(*) n, MAX(last_seen_at) seen FROM credentials WHERE player_id=? AND revoked_at IS NULL", (pid,)).fetchone()
        first_claim = c.execute("SELECT MIN(created_at) t FROM credentials WHERE player_id=?", (pid,)).fetchone()["t"]
        if creds["n"] == 0:
            claim = c.execute("SELECT MAX(created_at) t FROM claim_tokens WHERE player_id=?", (pid,)).fetchone()["t"]
            if claim is None or claim < db.plus(now, days=-3):
                out.append(dict(kind="never_claimed", player_id=pid, player=p["name"], detail="No phone set up yet. Send a new claim link."))
            continue
        total = c.execute("SELECT COUNT(*) n, MAX(server_ts) last FROM answers WHERE player_id=?", (pid,)).fetchone()
        hb = c.execute("SELECT * FROM heartbeats WHERE player_id=? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
        if hb is not None:
            if hb["sent"] is not None and hb["sent"] > total["n"]:
                out.append(dict(kind="possible_loss", player_id=pid, player=p["name"], detail=f"The phone says it sent {hb['sent']} answers; the server holds {total['n']}."))
            if hb["unsent"] and hb["ts"] < db.plus(now, hours=-UNSENT_HOURS) and (total["last"] is None or total["last"] < hb["ts"]):
                out.append(dict(kind="stale_unsent", player_id=pid, player=p["name"], detail=f"{hb['unsent']} answers unsent since {hb['ts'][:16]}. Ask him to open the app with signal."))
            try:
                rej = int(json.loads(hb["detail"] or "{}").get("rejected", 0))
            except (ValueError, TypeError, AttributeError):
                rej = 0
            if rej:
                out.append(dict(kind="rejected", player_id=pid, player=p["name"], detail=f"{rej} answers were refused by the server. See the audit log."))
        if (total["last"] is None or total["last"] < db.plus(now, days=-SILENT_DAYS)) and first_claim and first_claim < db.plus(now, days=-SILENT_DAYS):
            out.append(dict(kind="silent", player_id=pid, player=p["name"], detail=f"No answers in {SILENT_DAYS} days."))
    return out
