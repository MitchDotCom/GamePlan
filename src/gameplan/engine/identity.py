"""Who is this? Roster, claim links, pairing codes, recovery codes, device credentials and staff access.

Flow for a hitter (docs/ENGINE_PLAN.md section 5):
  staff create a claim token for a rostered player  ->  hitter opens the link, sees his name, confirms  ->  the app gets a device credential and a pairing code
  (the code lets the installed home-screen copy, which has separate storage, get its own credential)  ->  lost phone: staff issue a recovery code.
Rules: a name is never an identity; secrets are random, expire, are single-use where it matters and are stored only as keyed hashes; at most MAX_CREDENTIALS are active per player;
every event is written to audit_log. Error messages for bad tokens are deliberately the same whatever was wrong.
"""
from __future__ import annotations

import sqlite3

from . import db, security

MAX_CREDENTIALS = 2
MAX_SHARED = 3                 # sign-ins on shared iPads are disposable: past this the oldest is retired
SHARED_IDLE_HOURS = 8          # a shared sign-in nobody has touched for this long stops working
GUEST_MINUTES = 10
CLAIM_DAYS = 7
PAIR_MINUTES = 10
RECOVER_HOURS = 24
BAD = "That link or code is not valid. Ask a coach for a new one."


class EngineError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "error"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


# ---------------------------------------------------------------- teams, players, assignments
def add_team(c, name: str, level: str, mlb_team_id: int | None = None, sport_id: int | None = None, adapter: str = "none") -> int:
    with db.tx(c):
        cur = c.execute("INSERT INTO teams(name, level, mlb_team_id, sport_id, adapter) VALUES (?,?,?,?,?)", (name.strip(), level, mlb_team_id, sport_id, adapter))
        c.execute("INSERT INTO level_settings(team_id) VALUES (?)", (cur.lastrowid,))
        db.audit(c, "system", None, "team_added", dict(team_id=cur.lastrowid, name=name))
    return cur.lastrowid


def add_player(c, name: str, bats: str, team_id: int | None = None, org_id: str | None = None, mlbam_id: int | None = None, throws: str | None = None, start: str | None = None, actor: int | None = None) -> int:
    name = (name or "").strip()
    if not name or len(name) > 120:
        raise EngineError("A player needs a name of 1 to 120 characters.")
    if bats not in ("L", "R", "S"):
        raise EngineError("Bats must be L, R or S.")
    with db.tx(c):
        try:
            cur = c.execute("INSERT INTO players(org_id, mlbam_id, name, bats, throws, created_at) VALUES (?,?,?,?,?,?)", (org_id or None, mlbam_id, name, bats, throws, db.now()))
        except sqlite3.IntegrityError:
            raise EngineError(f"A player with org id {org_id} already exists.", 409, "duplicate")
        pid = cur.lastrowid
        if team_id is not None:
            c.execute("INSERT INTO assignments(player_id, team_id, start_date) VALUES (?,?,?)", (pid, team_id, start or db.today()))
        db.audit(c, "staff" if actor else "system", actor, "player_added", dict(player_id=pid, team_id=team_id))
    return pid


def assign(c, player_id: int, team_id: int, start: str | None = None, actor: int | None = None) -> None:
    """Move a player to a team (promotion, demotion, trade). The open assignment is closed the day before; history stays with the player."""
    start = start or db.today()
    with db.tx(c):
        cur = c.execute("SELECT id, start_date FROM assignments WHERE player_id=? AND end_date IS NULL", (player_id,)).fetchone()
        if cur is not None:
            if cur["start_date"] > start:
                raise EngineError("The new assignment starts before the current one.")
            c.execute("UPDATE assignments SET end_date=? WHERE id=?", (start if cur["start_date"] == start else _prev_day(start), cur["id"]))
        c.execute("INSERT INTO assignments(player_id, team_id, start_date) VALUES (?,?,?)", (player_id, team_id, start))
        db.audit(c, "staff" if actor else "system", actor, "assigned", dict(player_id=player_id, team_id=team_id, start=start))


def _prev_day(d: str) -> str:
    import datetime
    return (datetime.date.fromisoformat(d) - datetime.timedelta(days=1)).isoformat()


def current_assignment(c, player_id: int, on: str | None = None):
    on = on or db.today()
    return c.execute(
        "SELECT a.*, t.name team_name, t.level, t.adapter, t.mlb_team_id, t.sport_id FROM assignments a JOIN teams t ON t.id=a.team_id "
        "WHERE a.player_id=? AND a.start_date<=? AND (a.end_date IS NULL OR a.end_date>=?) ORDER BY a.start_date DESC LIMIT 1", (player_id, on, on)).fetchone()


def import_roster(c, rows: list[dict], actor: int | None = None) -> dict:
    """rows: name, bats, team (name), org_id (optional), mlbam_id (optional), throws (optional). A row that fails is reported and skipped; the rest are imported. Players are matched on org_id, never on name."""
    out = dict(added=0, updated=0, errors=[])
    teams = {r["name"]: r["id"] for r in c.execute("SELECT id, name FROM teams")}
    for i, r in enumerate(rows, start=1):
        try:
            team_id = teams.get((r.get("team") or "").strip())
            if team_id is None:
                raise EngineError(f"unknown team '{r.get('team')}'")
            oid = (r.get("org_id") or "").strip() or None
            existing = c.execute("SELECT id FROM players WHERE org_id=?", (oid,)).fetchone() if oid else None
            if existing:
                cur = current_assignment(c, existing["id"])
                if cur is None or cur["team_id"] != team_id:
                    assign(c, existing["id"], team_id, actor=actor)
                out["updated"] += 1
            else:
                add_player(c, r.get("name"), (r.get("bats") or "").strip().upper()[:1], team_id, oid, int(r["mlbam_id"]) if str(r.get("mlbam_id") or "").strip().isdigit() else None, (r.get("throws") or None), actor=actor)
                out["added"] += 1
        except EngineError as e:
            out["errors"].append(dict(row=i, name=r.get("name"), error=e.message))
    return out


# ---------------------------------------------------------------- claim, pairing, recovery
def _active_credentials(c, player_id: int) -> int:
    """His own phones: shared-iPad sign-ins do not use up a phone slot."""
    return c.execute("SELECT COUNT(*) n FROM credentials WHERE player_id=? AND revoked_at IS NULL AND shared=0", (player_id,)).fetchone()["n"]


def create_claim(c, secret: str, player_id: int, staff_id: int | None = None) -> str:
    """A fresh single-use claim token for a player; any earlier unused one is revoked."""
    if c.execute("SELECT 1 FROM players WHERE id=? AND active=1", (player_id,)).fetchone() is None:
        raise EngineError("No such active player.", 404)
    tok = security.new_token()
    with db.tx(c):
        c.execute("UPDATE claim_tokens SET revoked_at=? WHERE player_id=? AND used_at IS NULL AND revoked_at IS NULL", (db.now(), player_id))
        c.execute("INSERT INTO claim_tokens(player_id, token_hash, created_at, expires_at, created_by) VALUES (?,?,?,?,?)",
                  (player_id, security.keyed_hash(secret, tok), db.now(), db.plus(db.now(), days=CLAIM_DAYS), staff_id))
        db.audit(c, "staff", staff_id, "claim_created", dict(player_id=player_id))
    return tok


def _claim_row(c, secret: str, token: str):
    row = c.execute("SELECT * FROM claim_tokens WHERE token_hash=?", (security.keyed_hash(secret, token or ""),)).fetchone()
    if row is None or row["used_at"] or row["revoked_at"] or row["expires_at"] < db.now():
        return None
    return row


def player_card(c, player_id: int) -> dict:
    p = c.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    a = current_assignment(c, player_id)
    return dict(id=p["id"], name=p["name"], bats=p["bats"], throws=p["throws"], team=a["team_name"] if a else None, level=a["level"] if a else None, team_id=a["team_id"] if a else None)


def claim_preview(c, secret: str, token: str) -> dict:
    """What the hitter is asked to confirm. Does not use up the token."""
    row = _claim_row(c, secret, token)
    if row is None:
        raise EngineError(BAD, 404, "invalid")
    return player_card(c, row["player_id"])


def _new_credential(c, secret: str, player_id: int, label: str, via: str, shared: int = 0) -> tuple:
    tok = security.new_token(32)
    cur = c.execute("INSERT INTO credentials(player_id, token_hash, label, created_at, last_seen_at, via, shared) VALUES (?,?,?,?,?,?,?)",
                    (player_id, security.keyed_hash(secret, tok), (label or "")[:60], db.now(), db.now(), via, shared))
    return cur.lastrowid, tok


def _new_pair_code(c, secret: str, player_id: int, cred_id: int | None, keep_issuer: int = 0, staff_id: int | None = None) -> str:
    """keep_issuer=0: the home-screen app pairing code (redeeming it retires the browser credential that issued it). keep_issuer=1: a shared-iPad code (the issuer stays signed in)."""
    c.execute("UPDATE codes SET revoked_at=? WHERE kind='pair' AND player_id=? AND keep_issuer=? AND used_at IS NULL AND revoked_at IS NULL", (db.now(), player_id, keep_issuer))
    for _ in range(20):
        code = security.new_code(8)
        try:
            c.execute("INSERT INTO codes(kind, player_id, code_hash, from_credential_id, created_by, created_at, expires_at, keep_issuer) VALUES ('pair',?,?,?,?,?,?,?)",
                      (player_id, security.keyed_hash(secret, code), cred_id, staff_id, db.now(), db.plus(db.now(), minutes=GUEST_MINUTES if keep_issuer else PAIR_MINUTES), keep_issuer))
            return code
        except sqlite3.IntegrityError:
            continue
    raise EngineError("Could not issue a code. Try again.", 500)


def claim_confirm(c, secret: str, token: str, label: str = "") -> dict:
    """The hitter said 'yes, that is me'. Uses up the token and returns his device credential and an 8-digit pairing code for the installed home-screen app."""
    with db.tx(c):
        row = _claim_row(c, secret, token)
        if row is None:
            raise EngineError(BAD, 404, "invalid")
        pid = row["player_id"]
        if _active_credentials(c, pid) >= MAX_CREDENTIALS:
            raise EngineError("This player already has two phones set up. Ask a coach to remove one.", 409, "device_limit")
        cred_id, tok = _new_credential(c, secret, pid, label, "claim")
        c.execute("UPDATE claim_tokens SET used_at=? WHERE id=?", (db.now(), row["id"]))
        code = _new_pair_code(c, secret, pid, cred_id)
        db.audit(c, "player", pid, "claimed", dict(credential_id=cred_id, label=label))
    return dict(credential=tok, pairing_code=code, pairing_minutes=PAIR_MINUTES, player=player_card(c, pid))


def new_pairing_code(c, secret: str, player_id: int, credential_id: int) -> dict:
    """An already-signed-in phone asks for a fresh pairing code (to set up the installed app after the first code expired)."""
    with db.tx(c):
        code = _new_pair_code(c, secret, player_id, credential_id)
        db.audit(c, "player", player_id, "pair_code_issued", dict(credential_id=credential_id))
    return dict(pairing_code=code, pairing_minutes=PAIR_MINUTES)


def new_guest_code(c, secret: str, player_id: int, credential_id: int | None, staff_id: int | None = None) -> dict:
    """A code to sign in on a shared iPad. His phone (or a coach) issues it; redeeming it leaves the phone signed in."""
    with db.tx(c):
        code = _new_pair_code(c, secret, player_id, credential_id, 1, staff_id)
        db.audit(c, "staff" if staff_id else "player", staff_id or player_id, "guest_code_issued", dict(player_id=player_id, credential_id=credential_id))
    return dict(pairing_code=code, pairing_minutes=GUEST_MINUTES)


def _redeem(c, secret: str, kind: str, code: str):
    row = c.execute("SELECT * FROM codes WHERE kind=? AND code_hash=?", (kind, security.keyed_hash(secret, security.clean_code(code)))).fetchone()
    if row is None or row["used_at"] or row["revoked_at"] or row["expires_at"] < db.now():
        return None
    return row


def pair(c, secret: str, code: str, label: str = "") -> dict:
    """The installed home-screen app redeems the code and gets its own credential. The credential that issued the code is retired, so the player still has at most two."""
    with db.tx(c):
        row = _redeem(c, secret, "pair", code)
        if row is None:
            raise EngineError(BAD, 404, "invalid")
        pid = row["player_id"]
        if row["keep_issuer"]:
            old = c.execute("SELECT id FROM credentials WHERE player_id=? AND shared=1 AND revoked_at IS NULL ORDER BY id DESC", (pid,)).fetchall()
            for r in old[MAX_SHARED - 1:]:
                c.execute("UPDATE credentials SET revoked_at=?, revoked_reason='shared_replaced' WHERE id=?", (db.now(), r["id"]))
            cred_id, tok = _new_credential(c, secret, pid, label or "Shared iPad", "guest", 1)
            c.execute("UPDATE codes SET used_at=? WHERE id=?", (db.now(), row["id"]))
            db.audit(c, "player", pid, "guest_signin", dict(credential_id=cred_id))
            return dict(credential=tok, player=player_card(c, pid), shared=True)
        if row["from_credential_id"]:
            c.execute("UPDATE credentials SET revoked_at=?, revoked_reason='replaced_by_pairing' WHERE id=? AND revoked_at IS NULL", (db.now(), row["from_credential_id"]))
        if _active_credentials(c, pid) >= MAX_CREDENTIALS:
            raise EngineError("This player already has two phones set up. Ask a coach to remove one.", 409, "device_limit")
        cred_id, tok = _new_credential(c, secret, pid, label, "pair")
        c.execute("UPDATE codes SET used_at=? WHERE id=?", (db.now(), row["id"]))
        db.audit(c, "player", pid, "paired", dict(credential_id=cred_id))
    return dict(credential=tok, player=player_card(c, pid))


def create_recovery(c, secret: str, player_id: int, staff_id: int | None) -> dict:
    """A coach hands a hitter who lost his phone an 8-digit code. Redeeming it retires every older credential."""
    if c.execute("SELECT 1 FROM players WHERE id=? AND active=1", (player_id,)).fetchone() is None:
        raise EngineError("No such active player.", 404)
    with db.tx(c):
        c.execute("UPDATE codes SET revoked_at=? WHERE kind='recover' AND player_id=? AND used_at IS NULL AND revoked_at IS NULL", (db.now(), player_id))
        for _ in range(20):
            code = security.new_code(8)
            try:
                c.execute("INSERT INTO codes(kind, player_id, code_hash, created_by, created_at, expires_at) VALUES ('recover',?,?,?,?,?)",
                          (player_id, security.keyed_hash(secret, code), staff_id, db.now(), db.plus(db.now(), hours=RECOVER_HOURS)))
                break
            except sqlite3.IntegrityError:
                continue
        db.audit(c, "staff", staff_id, "recovery_issued", dict(player_id=player_id))
    return dict(code=code, hours=RECOVER_HOURS)


def recover(c, secret: str, code: str, label: str = "") -> dict:
    with db.tx(c):
        row = _redeem(c, secret, "recover", code)
        if row is None:
            raise EngineError(BAD, 404, "invalid")
        pid = row["player_id"]
        c.execute("UPDATE credentials SET revoked_at=?, revoked_reason='recovery' WHERE player_id=? AND revoked_at IS NULL", (db.now(), pid))
        cred_id, tok = _new_credential(c, secret, pid, label, "recover")
        c.execute("UPDATE codes SET used_at=? WHERE id=?", (db.now(), row["id"]))
        db.audit(c, "player", pid, "recovered", dict(credential_id=cred_id))
    return dict(credential=tok, player=player_card(c, pid))


def authenticate(c, secret: str, bearer: str | None):
    """-> (credential row, player row) for a live credential, else None. last_seen is touched at most once a minute to keep reads cheap."""
    if not bearer or len(bearer) > 200:
        return None
    cred = c.execute("SELECT * FROM credentials WHERE token_hash=? AND revoked_at IS NULL", (security.keyed_hash(secret, bearer),)).fetchone()
    if cred is None:
        return None
    if cred["shared"] and (cred["last_seen_at"] or "") < db.plus(db.now(), hours=-SHARED_IDLE_HOURS):
        c.execute("UPDATE credentials SET revoked_at=?, revoked_reason='shared_idle' WHERE id=? AND revoked_at IS NULL", (db.now(), cred["id"]))
        return None
    player = c.execute("SELECT * FROM players WHERE id=? AND active=1", (cred["player_id"],)).fetchone()
    if player is None:
        return None
    if not cred["last_seen_at"] or cred["last_seen_at"] < db.plus(db.now(), seconds=-60):
        c.execute("UPDATE credentials SET last_seen_at=? WHERE id=?", (db.now(), cred["id"]))
    return cred, player


def revoke_credential(c, credential_id: int, staff_id: int | None, reason: str = "staff") -> None:
    with db.tx(c):
        c.execute("UPDATE credentials SET revoked_at=?, revoked_reason=? WHERE id=? AND revoked_at IS NULL", (db.now(), reason, credential_id))
        db.audit(c, "staff", staff_id, "credential_revoked", dict(credential_id=credential_id, reason=reason))


def sign_out(c, credential_id: int) -> None:
    """The hitter taps 'not me': his own credential is retired."""
    with db.tx(c):
        c.execute("UPDATE credentials SET revoked_at=?, revoked_reason='signed_out' WHERE id=? AND revoked_at IS NULL", (db.now(), credential_id))
        db.audit(c, "player", None, "signed_out", dict(credential_id=credential_id))


def delete_player_data(c, player_id: int, staff_id: int | None) -> dict:
    """A hitter asks for his data to go. Everything tied to him is removed (answers, corrections, heartbeats, devices, codes, consents, playlists); the player row stays only as an
    anonymous placeholder so the audit trail keeps its references. Admin action; the audit entry records counts, not the name."""
    with db.tx(c):
        if c.execute("SELECT 1 FROM players WHERE id=?", (player_id,)).fetchone() is None:
            raise EngineError("No such player.", 404)
        n = {}
        n["voids"] = c.execute("DELETE FROM voids WHERE answer_id IN (SELECT id FROM answers WHERE player_id=?)", (player_id,)).rowcount
        for t in ("answers", "heartbeats", "playlists", "consents", "codes", "claim_tokens", "credentials", "assignments"):
            n[t] = c.execute(f"DELETE FROM {t} WHERE player_id=?", (player_id,)).rowcount
        c.execute("UPDATE players SET name=?, org_id=NULL, mlbam_id=NULL, active=0 WHERE id=?", (f"Deleted hitter {player_id}", player_id))
        db.audit(c, "staff", staff_id, "player.data_deleted", dict(player_id=player_id, removed=n))
    return n


# ---------------------------------------------------------------- staff
def create_staff(c, secret: str, name: str, role: str, team_ids: list[int] | None = None, actor: int | None = None, token: str | None = None) -> tuple:
    if role not in ("admin", "coach"):
        raise EngineError("Role must be admin or coach.")
    if token is not None and len(token) < 24:
        raise EngineError("A supplied staff token must be at least 24 characters.")
    tok = token or security.new_token(32)
    with db.tx(c):
        cur = c.execute("INSERT INTO staff(name, role, token_hash, created_at) VALUES (?,?,?,?)", (name.strip(), role, security.keyed_hash(secret, tok), db.now()))
        for t in team_ids or []:
            c.execute("INSERT INTO staff_teams(staff_id, team_id) VALUES (?,?)", (cur.lastrowid, t))
        db.audit(c, "staff", actor, "staff_created", dict(staff_id=cur.lastrowid, role=role, teams=team_ids or []))
    return cur.lastrowid, tok


def authenticate_staff(c, secret: str, token: str | None):
    if not token or len(token) > 200:
        return None
    return c.execute("SELECT * FROM staff WHERE token_hash=? AND revoked_at IS NULL", (security.keyed_hash(secret, token),)).fetchone()


def staff_team_ids(c, staff) -> list[int] | None:
    """None means every team (admin). Otherwise the teams this coach may see."""
    if staff["role"] == "admin":
        return None
    return [r["team_id"] for r in c.execute("SELECT team_id FROM staff_teams WHERE staff_id=?", (staff["id"],))]


def staff_can_see_player(c, staff, player_id: int) -> bool:
    ids = staff_team_ids(c, staff)
    if ids is None:
        return True
    a = current_assignment(c, player_id)
    hist = c.execute("SELECT DISTINCT team_id FROM assignments WHERE player_id=?", (player_id,)).fetchall()
    return bool(a and a["team_id"] in ids) or any(h["team_id"] in ids for h in hist)
