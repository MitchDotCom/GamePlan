"""Recording answers. The server is the authority: it checks the credential, checks the pack and item exist and belong to the player's team history, recomputes the key and the score from its own
tables (the phone's claim is kept only to spot phone bugs), copies the pitch facts from the pack, stamps the team and level that applied, and inserts idempotently on the answer id.

An answer is rejected with a named reason, never stored half-checked. Sending the same answer twice, or in a different order, stores one row.
"""
from __future__ import annotations

import json

from . import db, identity

MAX_BATCH = 500
TASKS = ("zone", "pitch")
MODES = ("train", "assess")
STRIKE_BALL = ("Strike", "Ball")


def _text(x, n: int):
    return None if x is None else str(x)[:n]


def _int(x, lo: int, hi: int):
    if x is None or x == "":
        return None
    v = int(float(x))
    if not lo <= v <= hi:
        raise ValueError("out of range")
    return v


def clean(a: dict) -> dict:
    """Shape and range checks on one phone-supplied answer. Raises ValueError with a short reason."""
    if not isinstance(a, dict):
        raise ValueError("not an object")
    aid = str(a.get("id") or "")
    if not 8 <= len(aid) <= 64 or not all(ch.isalnum() or ch in "-_" for ch in aid):
        raise ValueError("bad id")
    if a.get("task") not in TASKS:
        raise ValueError("bad task")
    if a.get("mode") not in MODES:
        raise ValueError("bad mode")
    call = str(a.get("call") or "")
    if not 1 <= len(call) <= 32:
        raise ValueError("bad call")
    return dict(id=aid, task=a["task"], mode=a["mode"], call=call, pack=str(a.get("pack") or "")[:80], item=str(a.get("clip") or a.get("item") or "")[:80],
                options=_text(a.get("options"), 200), rt_ms=_int(a.get("rt_ms"), 0, 600000), pause_ms=_int(a.get("pause_ms"), 0, 3000), camera=_text(a.get("camera"), 40), view=_text(a.get("view"), 40),
                q_order=_int(a.get("q_order"), 0, 5), clip_trial=_int(a.get("clip_trial"), 0, 10 ** 6), session=_text(a.get("session"), 40),
                client_correct=None if a.get("correct") in (None, "") else int(float(a["correct"])) if str(a.get("correct")) in ("0", "1", "0.0", "1.0") else None,
                device_ts=_text(a.get("ts"), 40), app_version=_text(a.get("app"), 20), content_version=_text(a.get("pack"), 80))


def _pack_items(c, cache: dict, pack_hash: str):
    if pack_hash not in cache:
        row = c.execute("SELECT * FROM packs WHERE hash=?", (pack_hash,)).fetchone()
        cache[pack_hash] = None if row is None else (row, {i["id"]: i for i in json.loads(row["manifest_json"])["items"]})
    return cache[pack_hash]


def _allowed_teams(c, player_id: int) -> set:
    return {r["team_id"] for r in c.execute("SELECT DISTINCT team_id FROM assignments WHERE player_id=?", (player_id,))}


def ingest(c, player, credential, answers: list, server_ts: str | None = None) -> dict:
    """-> {stored: [ids], duplicates: [ids], rejected: [{id, reason}]}. Whole-batch failures raise; per-answer problems are reported per answer so one bad row never blocks the rest."""
    if not isinstance(answers, list):
        raise identity.EngineError("answers must be a list")
    if len(answers) > MAX_BATCH:
        raise identity.EngineError(f"at most {MAX_BATCH} answers per request", 413)
    server_ts = server_ts or db.now()
    out = dict(stored=[], duplicates=[], rejected=[])
    cache: dict = {}
    teams = _allowed_teams(c, player["id"])
    with db.tx(c):
        for raw in answers:
            rid = raw.get("id") if isinstance(raw, dict) else None
            try:
                a = clean(raw)
                got = _pack_items(c, cache, a["pack"])
                if got is None:
                    raise ValueError("unknown pack")
                prow, items = got
                if prow["team_id"] is not None and prow["team_id"] not in teams:
                    raise ValueError("pack is not for this player")
                it = items.get(a["item"])
                if it is None:
                    raise ValueError("unknown item")
                if a["mode"] != prow["mode"]:
                    raise ValueError("mode does not match the pack")
                if a["task"] == "pitch" and a["call"] not in (it.get("arsenal") or []):
                    raise ValueError("call is not one of the offered pitch types")
                if a["task"] == "zone" and a["call"] not in STRIKE_BALL:
                    raise ValueError("call must be Strike or Ball")
                k = c.execute("SELECT strike, pitch_type FROM item_keys WHERE pack_hash=? AND item_id=?", (a["pack"], a["item"])).fetchone()
                if k is None:
                    raise ValueError("no key on file")
                key = (None if k["strike"] is None else ("Strike" if k["strike"] else "Ball")) if a["task"] == "zone" else k["pitch_type"]
                correct = None if key is None else int(a["call"] == key)
                m = it.get("meta") or {}
                existing = c.execute("SELECT player_id FROM answers WHERE id=?", (a["id"],)).fetchone()
                if existing is not None:
                    if existing["player_id"] != player["id"]:
                        raise ValueError("id belongs to another record")
                    out["duplicates"].append(a["id"])
                    continue
                asg = identity.current_assignment(c, player["id"], (a["device_ts"] or server_ts)[:10] if (a["device_ts"] or "")[:4].isdigit() else server_ts[:10]) or identity.current_assignment(c, player["id"], server_ts[:10])
                c.execute(
                    "INSERT INTO answers(id, player_id, credential_id, team_id, level, session, pack_hash, item_id, task, mode, call, options, rt_ms, pause_ms, camera, view, q_order, clip_trial, key, correct, client_correct, "
                    "stand, pitch_type, family, pocket, px, pz, sz_top, sz_bot, speed, device_ts, server_ts, app_version, content_version) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                    (a["id"], player["id"], credential["id"], asg["team_id"] if asg else None, asg["level"] if asg else None, a["session"], a["pack"], a["item"], a["task"], a["mode"], a["call"], a["options"],
                     a["rt_ms"], a["pause_ms"], it.get("camera") or a["camera"], a["view"], a["q_order"], a["clip_trial"], key, correct, a["client_correct"], m.get("stand"), m.get("pitch_type"), m.get("family"),
                     m.get("pocket"), m.get("px"), m.get("pz"), m.get("sz_top"), m.get("sz_bot"), m.get("speed"), a["device_ts"], server_ts, a["app_version"], a["content_version"]))
                out["stored"].append(a["id"])
            except (ValueError, TypeError) as e:
                out["rejected"].append(dict(id=rid if isinstance(rid, str) else None, reason=str(e)[:80]))
    return out


def void(c, answer_id: str, reason: str, staff_id: int | None) -> None:
    if not reason or not reason.strip():
        raise identity.EngineError("A reason is required to void an answer.")
    with db.tx(c):
        if c.execute("SELECT 1 FROM answers WHERE id=?", (answer_id,)).fetchone() is None:
            raise identity.EngineError("No such answer.", 404)
        c.execute("INSERT OR IGNORE INTO voids(answer_id, reason, staff_id, voided_at) VALUES (?,?,?,?)", (answer_id, reason.strip()[:200], staff_id, db.now()))
        db.audit(c, "staff", staff_id, "answer_voided", dict(answer_id=answer_id, reason=reason[:200]))


LIVE = "id NOT IN (SELECT answer_id FROM voids)"
