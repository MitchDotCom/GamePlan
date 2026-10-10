"""The weekly slate: which opposing starter each affiliate's hitters see, and when it changes.

One row in `starters` is one game: (team, game date, game number) -> the opposing starter. Many dates can be confirmed at once, so a whole week can be entered on an off day and built ahead.

The rule a hitter's phone lives by (docs/SCHEDULE_PLAN.md):
  * the slate day is the team-local date, moved forward one day once the local clock passes the rollover hour (default 21:00 Pacific, so the next opponent is ready right after the game);
  * an admin can pin the slate day for one team (rain delay, game ended early) with a hold that expires on its own;
  * the hitter sees the confirmed starters of the first game date on or after the slate day, within LOOKAHEAD_DAYS (a doubleheader shows both);
  * a date with nothing confirmed is said so. Nothing is ever guessed and a different starter is never shown in its place.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from . import db, identity

DEFAULT_TZ = "America/Los_Angeles"
DEFAULT_HOUR = 21
LOOKAHEAD_DAYS = 10
MAX_HOLD_HOURS = 72
MAX_GAME_NO = 3
BUILDABLE = ("mlb_video", "tracking_drawn")
UTC = dt.timezone.utc


def parse_utc(iso: str) -> dt.datetime:
    return dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def to_iso(t: dt.datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _date(s: str) -> dt.date:
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise identity.EngineError("A date looks like 2027-04-12.", 400)
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise identity.EngineError("That is not a real date.", 400)


def clock(c, team_id: int) -> tuple:
    """-> (ZoneInfo, rollover hour) for a team. A bad stored zone falls back to Pacific rather than breaking every hitter's playlist."""
    r = c.execute("SELECT rollover_tz, rollover_hour FROM level_settings WHERE team_id=?", (team_id,)).fetchone()
    tz, hour = (r["rollover_tz"], r["rollover_hour"]) if r else (DEFAULT_TZ, DEFAULT_HOUR)
    try:
        z = ZoneInfo(tz)
    except Exception:
        z = ZoneInfo(DEFAULT_TZ)
    return z, hour if isinstance(hour, int) and 12 <= hour <= 23 else DEFAULT_HOUR


def _change_at(day: dt.date, tz: ZoneInfo, hour: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour), tzinfo=tz)


def natural_day(c, team_id: int, now_iso: str) -> tuple:
    """-> (slate date, the instant it next changes by the clock alone). The rollover hour is 12 to 23, so a daylight-saving jump (always in the small hours) never lands on it."""
    tz, hour = clock(c, team_id)
    local = parse_utc(now_iso).astimezone(tz)
    if local.hour >= hour:
        return local.date() + dt.timedelta(days=1), _change_at(local.date() + dt.timedelta(days=1), tz, hour)
    return local.date(), _change_at(local.date(), tz, hour)


def active_hold(c, team_id: int, now_iso: str):
    return c.execute("SELECT * FROM slate_holds WHERE team_id=? AND cleared_at IS NULL AND until_utc>? ORDER BY set_at DESC, id DESC LIMIT 1", (team_id, now_iso)).fetchone()


def slate_day(c, team_id: int, now_iso: str | None = None) -> dict:
    now_iso = now_iso or db.now()
    day, change = natural_day(c, team_id, now_iso)
    h = active_hold(c, team_id, now_iso)
    if h is not None:
        return dict(date=h["pin_date"], valid_until=h["until_utc"], source="hold", hold=dict(h))
    return dict(date=day.isoformat(), valid_until=to_iso(change), source="clock", hold=None)


def entries_from(c, team_id: int, day: str, *, after: bool = False) -> list:
    """The confirmed games of the first game date on or after `day` (strictly after it when after=True), within the lookahead. [] when none."""
    d = _date(day)
    lo = (d + dt.timedelta(days=1 if after else 0)).isoformat()
    hi = (d + dt.timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    rows = c.execute("SELECT * FROM starters WHERE team_id=? AND status='confirmed' AND game_date>=? AND game_date<=? ORDER BY game_date, game_no, id DESC", (team_id, lo, hi)).fetchall()
    if not rows:
        return []
    first, seen, out = rows[0]["game_date"], set(), []
    for r in rows:
        if r["game_date"] == first and r["game_no"] not in seen:        # id DESC: the newest confirmation of a game wins
            seen.add(r["game_no"])
            out.append(r)
    return sorted(out, key=lambda r: r["game_no"])


def resolve(c, team_id: int, now_iso: str | None = None) -> dict:
    """-> dict(day, source, hold, valid_until, game_date, entries). `entries` is empty when nothing is confirmed in the lookahead."""
    now_iso = now_iso or db.now()
    sd = slate_day(c, team_id, now_iso)
    es = entries_from(c, team_id, sd["date"])
    return dict(day=sd["date"], source=sd["source"], hold=sd["hold"], valid_until=sd["valid_until"], entries=es, game_date=es[0]["game_date"] if es else None)


# ---------------------------------------------------------------------------- writing the schedule
def _clean_name(s) -> str:
    s = " ".join(str(s or "").split())
    if not s:
        raise identity.EngineError("A starter needs a name.", 400)
    if len(s) > 120:
        raise identity.EngineError("That name is too long.", 400)
    return s


def _clean_id(v):
    if v in (None, ""):
        return None
    s = str(v).strip()
    if not re.fullmatch(r"\d{1,10}", s) or int(s) <= 0:
        raise identity.EngineError("A player id is digits only.", 400)
    return int(s)


def _retire_packs(c, starter_id: int) -> None:
    c.execute("UPDATE packs SET status='retired' WHERE starter_id=? AND status='active'", (starter_id,))


def _put(c, team_id: int, game_date: str, game_no: int, name: str, pid, opponent, staff_id, source: str, strict: bool, today: str) -> dict:
    """Caller holds the write transaction. Idempotent: the same starter, id and opponent for a game is left exactly as it is, so saving a grid again never rebuilds anything."""
    d = _date(game_date)
    if not isinstance(game_no, int) or not 1 <= game_no <= MAX_GAME_NO:
        raise identity.EngineError("Game number is 1 to 3.", 400)
    if strict:
        t = dt.date.fromisoformat(today)
        if d < t - dt.timedelta(days=1) or d > t + dt.timedelta(days=120):
            raise identity.EngineError(f"{game_date} is outside the window (yesterday to 120 days ahead). Check the year.", 400)
    t = c.execute("SELECT * FROM teams WHERE id=? AND active=1", (team_id,)).fetchone()
    if t is None:
        raise identity.EngineError("No such affiliate.", 404)
    name, pid = _clean_name(name), _clean_id(pid)
    opponent = " ".join(str(opponent or "").split())[:80] or None
    warnings = []
    cur = c.execute("SELECT * FROM starters WHERE team_id=? AND game_date=? AND game_no=? AND status='confirmed' ORDER BY id DESC LIMIT 1", (team_id, game_date, game_no)).fetchone()
    if cur is not None and cur["pitcher_name"] == name and cur["pitcher_id"] == pid and (cur["opponent"] or None) == opponent:
        return dict(id=cur["id"], changed=False, warnings=[])
    if pid is None:
        warnings.append("No player id: pitches cannot be built until it is added.")
    else:
        other = c.execute("SELECT pitcher_name FROM starters WHERE pitcher_id=? AND pitcher_name<>? AND status IN ('confirmed','superseded') ORDER BY id DESC LIMIT 1", (pid, name)).fetchone()
        if other is not None:
            warnings.append(f"Id {pid} was entered before as {other['pitcher_name']}. Check the id.")
    if t["adapter"] not in BUILDABLE:
        warnings.append(f"{t['name']} has no pitch source, so hitters will see practice pitches with this starter named.")
    for old in c.execute("SELECT id FROM starters WHERE team_id=? AND game_date=? AND game_no=? AND status IN ('confirmed','suggested','tbd')", (team_id, game_date, game_no)).fetchall():
        _retire_packs(c, old["id"])
    c.execute("UPDATE starters SET status='superseded' WHERE team_id=? AND game_date=? AND game_no=? AND status IN ('confirmed','suggested','tbd')", (team_id, game_date, game_no))
    state = "queued" if (pid is not None and t["adapter"] in BUILDABLE) else ""
    new = c.execute("INSERT INTO starters(team_id, game_date, game_no, game_pk, pitcher_id, pitcher_name, opponent, status, source, checked_at, confirmed_by, confirmed_at, season, build_state) "
                    "VALUES (?,?,?,NULL,?,?,?,'confirmed',?,?,?,?,?,?)", (team_id, game_date, game_no, pid, name, opponent, source, db.now(), staff_id, db.now(), int(game_date[:4]), state)).lastrowid
    db.audit(c, "staff", staff_id, "starter_confirmed", dict(team_id=team_id, game_date=game_date, game_no=game_no, pitcher_id=pid, pitcher_name=name, opponent=opponent, replaced=cur["pitcher_name"] if cur else None))
    return dict(id=new, changed=True, warnings=warnings)


def set_entry(c, team_id: int, game_date: str, pitcher_name: str, pitcher_id=None, opponent=None, staff_id=None, game_no: int = 1, source: str = "staff", strict: bool = False) -> dict:
    with db.tx(c):
        return _put(c, team_id, game_date, game_no, pitcher_name, pitcher_id, opponent, staff_id, source, strict, db.local_today())


def cancel_entry(c, team_id: int, game_date: str, game_no: int, staff_id, reason: str = "") -> bool:
    """Postponed or removed. The row is kept as 'rejected' (never deleted) and its packs stop being served."""
    _date(game_date)
    with db.tx(c):
        rows = c.execute("SELECT id FROM starters WHERE team_id=? AND game_date=? AND game_no=? AND status IN ('confirmed','suggested','tbd')", (team_id, game_date, game_no)).fetchall()
        for r in rows:
            _retire_packs(c, r["id"])
        c.execute("UPDATE starters SET status='rejected' WHERE team_id=? AND game_date=? AND game_no=? AND status IN ('confirmed','suggested','tbd')", (team_id, game_date, game_no))
        if rows:
            db.audit(c, "staff", staff_id, "starter_cancelled", dict(team_id=team_id, game_date=game_date, game_no=game_no, reason=(reason or "")[:200]))
    return bool(rows)


def apply_grid(c, edits: list, staff_id, today: str | None = None) -> dict:
    """edits: dicts with team_id, game_date, game_no, and either clear=True or name/id/opp. All or nothing: any invalid cell stops the whole save and every problem is reported at once."""
    today = today or db.local_today()
    errors, plan = [], []
    for e in edits:
        label = f"{e.get('team_name') or e['team_id']} {e['game_date']}" + (f" game {e['game_no']}" if e["game_no"] != 1 else "")
        try:
            _date(e["game_date"])
            if not e.get("clear"):
                _clean_name(e.get("name"))
                _clean_id(e.get("id"))
            plan.append(e)
        except identity.EngineError as x:
            errors.append(f"{label}: {x.message}")
    if errors:
        return dict(saved=0, unchanged=0, cancelled=0, errors=errors, warnings=[])
    saved = unchanged = cancelled = 0
    warnings = []
    try:
        with db.tx(c):
            for e in plan:
                label = f"{e.get('team_name') or e['team_id']} {e['game_date']}"
                if e.get("clear"):
                    rows = c.execute("SELECT id FROM starters WHERE team_id=? AND game_date=? AND game_no=? AND status IN ('confirmed','suggested','tbd')", (e["team_id"], e["game_date"], e["game_no"])).fetchall()
                    for r in rows:
                        _retire_packs(c, r["id"])
                    c.execute("UPDATE starters SET status='rejected' WHERE team_id=? AND game_date=? AND game_no=? AND status IN ('confirmed','suggested','tbd')", (e["team_id"], e["game_date"], e["game_no"]))
                    if rows:
                        cancelled += 1
                        db.audit(c, "staff", staff_id, "starter_cancelled", dict(team_id=e["team_id"], game_date=e["game_date"], game_no=e["game_no"]))
                    continue
                r = _put(c, e["team_id"], e["game_date"], e["game_no"], e["name"], e.get("id"), e.get("opp"), staff_id, "staff", True, today)
                saved += r["changed"]
                unchanged += not r["changed"]
                warnings += [f"{label}: {w}" for w in r["warnings"]]
    except identity.EngineError as x:                                    # rolled back as a whole
        return dict(saved=0, unchanged=0, cancelled=0, errors=[x.message], warnings=[])
    return dict(saved=saved, unchanged=unchanged, cancelled=cancelled, errors=[], warnings=warnings)


# ---------------------------------------------------------------------------- holds (rain delay, early finish)
def set_hold(c, team_id: int, pin_date: str, until_iso: str, reason: str, staff_id, now_iso: str | None = None, max_hours: int = MAX_HOLD_HOURS) -> int:
    """Keep showing `pin_date`'s slate for this team until `until_iso`. It expires by itself; a forgotten hold cannot strand a team on an old starter."""
    now_iso = now_iso or db.now()
    _date(pin_date)
    if c.execute("SELECT 1 FROM teams WHERE id=? AND active=1", (team_id,)).fetchone() is None:
        raise identity.EngineError("No such affiliate.", 404)
    try:
        until = parse_utc(until_iso)
    except ValueError:
        raise identity.EngineError("That end time is not valid.", 400)
    now = parse_utc(now_iso)
    if until <= now:
        raise identity.EngineError("The end time is already past.", 400)
    if until - now > dt.timedelta(hours=max_hours):
        raise identity.EngineError(f"A hold lasts at most {max_hours} hours. Change the schedule for anything longer.", 400)
    with db.tx(c):
        c.execute("UPDATE slate_holds SET cleared_at=? WHERE team_id=? AND cleared_at IS NULL", (now_iso, team_id))
        hid = c.execute("INSERT INTO slate_holds(team_id, pin_date, until_utc, reason, set_by, set_at) VALUES (?,?,?,?,?,?)", (team_id, pin_date, to_iso(until), (reason or "")[:200], staff_id, now_iso)).lastrowid
        db.audit(c, "staff", staff_id, "slate_hold_set", dict(team_id=team_id, pin_date=pin_date, until=to_iso(until), reason=(reason or "")[:200]))
    return hid


def hold_current_day(c, team_id: int, until_local: str, reason: str, staff_id, now_iso: str | None = None) -> int:
    """Rain delay: keep what hitters see right now until a team-local time ('2027-05-04T23:30')."""
    now_iso = now_iso or db.now()
    tz, _ = clock(c, team_id)
    try:
        until = dt.datetime.fromisoformat(until_local).replace(tzinfo=tz)
    except ValueError:
        raise identity.EngineError("That end time is not valid.", 400)
    return set_hold(c, team_id, slate_day(c, team_id, now_iso)["date"], to_iso(until), reason, staff_id, now_iso)


def advance(c, team_id: int, staff_id, now_iso: str | None = None) -> str:
    """Show the next game's starter now instead of waiting for the rollover hour. Returns the date shown, or raises when nothing is confirmed after the current one."""
    now_iso = now_iso or db.now()
    r = resolve(c, team_id, now_iso)
    if not r["entries"]:
        raise identity.EngineError("Nothing is confirmed after the current game.", 409)
    nxt = entries_from(c, team_id, r["game_date"], after=True)
    if not nxt:
        raise identity.EngineError("Nothing is confirmed after the current game.", 409)
    pin = nxt[0]["game_date"]
    tz, hour = clock(c, team_id)
    until = _change_at(dt.date.fromisoformat(pin) - dt.timedelta(days=1), tz, hour)       # from then on the clock alone shows it
    if to_iso(until) <= now_iso:
        raise identity.EngineError("That game is already showing.", 409)
    set_hold(c, team_id, pin, to_iso(until), "advanced early", staff_id, now_iso, max_hours=24 * (LOOKAHEAD_DAYS + 1))
    return pin


def clear_hold(c, team_id: int, staff_id, now_iso: str | None = None) -> bool:
    now_iso = now_iso or db.now()
    with db.tx(c):
        n = c.execute("UPDATE slate_holds SET cleared_at=? WHERE team_id=? AND cleared_at IS NULL", (now_iso, team_id)).rowcount
        if n:
            db.audit(c, "staff", staff_id, "slate_hold_cleared", dict(team_id=team_id))
    return bool(n)


# ---------------------------------------------------------------------------- what the page and the checks show
def content_state(c, starter_id: int) -> str:
    """'ready' = a training pack on each side, 'partial' = only one side, 'none' = nothing registered."""
    sides = {r["side"] for r in c.execute("SELECT DISTINCT side FROM packs WHERE starter_id=? AND status='active' AND practice=0 AND mode='train'", (starter_id,))}
    return "ready" if {"L", "R"} <= sides else "partial" if sides else "none"


def week(c, team_ids: list, start: str, days: int = 7) -> dict:
    d0 = _date(start)
    dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(days)]
    rows = []
    for t in c.execute("SELECT * FROM teams WHERE active=1 ORDER BY level, name").fetchall():
        if team_ids is not None and t["id"] not in team_ids:
            continue
        cells = {d: [] for d in dates}
        for s in c.execute("SELECT * FROM starters WHERE team_id=? AND game_date>=? AND game_date<=? AND status IN ('confirmed','suggested','tbd') ORDER BY game_date, game_no, id", (t["id"], dates[0], dates[-1])):
            e = dict(s)
            e["content"] = content_state(c, s["id"]) if s["status"] == "confirmed" else ""
            cells[s["game_date"]].append(e)
        rows.append(dict(team=dict(t), cells=cells, hold=active_hold(c, t["id"], db.now())))
    return dict(dates=dates, rows=rows)


def preview(c, team_ids: list | None, now_iso: str | None = None, at_next: bool = False) -> list:
    """What every active hitter would be shown at `now_iso`, per team. Uses the same code path as the phone and writes nothing."""
    from . import playlist
    now_iso = now_iso or db.now()
    out = []
    for t in c.execute("SELECT * FROM teams WHERE active=1 ORDER BY level, name").fetchall():
        if team_ids is not None and t["id"] not in team_ids:
            continue
        r = resolve(c, t["id"], now_iso)
        when = now_iso
        if at_next:                                                  # one second after this team's next switch (clock or end of a hold)
            when = to_iso(parse_utc(r["valid_until"]) + dt.timedelta(seconds=1))
            r = resolve(c, t["id"], when)
        hitters, problems = [], []
        for p in c.execute("SELECT p.* FROM players p JOIN assignments a ON a.player_id=p.id WHERE p.active=1 AND a.team_id=? AND a.start_date<=? AND (a.end_date IS NULL OR a.end_date>=?) ORDER BY p.name", (t["id"], r["day"], r["day"])).fetchall():
            pl = playlist.compose(c, p, now_iso=when, record=False)
            starter_packs = [m for m in pl["packs"] if m.get("mode") == "train" and not m.get("practice")]
            practice = any(m.get("practice") for m in pl["packs"])
            kind = "starter" if starter_packs else "practice" if practice else "nothing"
            hitters.append(dict(id=p["id"], name=p["name"], bats=p["bats"], kind=kind, starter=pl.get("starter_names", [])))
        if not r["entries"]:
            problems.append("No starter is confirmed for the next game. Hitters see practice pitches.")
        for e in r["entries"]:
            if e["pitcher_id"] is None:
                problems.append(f"{e['pitcher_name']} ({e['game_date']}) has no player id, so no pitches can be built.")
            elif (t["adapter"] in BUILDABLE or e["content_kind"] == "comp") and content_state(c, e["id"]) != "ready":
                problems.append(f"{e['pitcher_name']} ({e['game_date']}): pitches are {content_state(c, e['id'])} ({e['build_state'] or 'not built'}).")
        bad = [h["name"] for h in hitters if h["kind"] != "starter"]
        if r["entries"] and bad:
            problems.append(f"{len(bad)} of {len(hitters)} hitters would not see the starter's pitches: {', '.join(bad[:6])}{'...' if len(bad) > 6 else ''}.")
        out.append(dict(team=dict(t), day=r["day"], source=r["source"], valid_until=r["valid_until"], entries=[dict(e) for e in r["entries"]], hitters=hitters, problems=problems))
    return out


def attention(c, team_ids: list | None, now_iso: str | None = None, ahead_days: int = 7) -> list:
    """Plain sentences for the Today page: what would leave a hitter without his starter, found now rather than that night."""
    now_iso = now_iso or db.now()
    out = []
    for t in c.execute("SELECT * FROM teams WHERE active=1 ORDER BY level, name").fetchall():
        if team_ids is not None and t["id"] not in team_ids:
            continue
        r = resolve(c, t["id"], now_iso)
        if not r["entries"]:
            out.append(f"{t['name']}: no starter is confirmed for the next game. Hitters see practice pitches.")
        if r["hold"]:
            out.append(f"{t['name']}: a hold is active (set for {r['hold']['pin_date']}), ending {r['hold']['until_utc'][:16].replace('T', ' ')} UTC.")
        hi = (dt.date.fromisoformat(r["day"]) + dt.timedelta(days=ahead_days)).isoformat()
        for e in c.execute("SELECT * FROM starters WHERE team_id=? AND status='confirmed' AND game_date>=? AND game_date<=? ORDER BY game_date, game_no", (t["id"], r["day"], hi)):
            if e["pitcher_id"] is None:
                out.append(f"{t['name']} {e['game_date']}: {e['pitcher_name']} has no player id.")
            elif (t["adapter"] in BUILDABLE or e["content_kind"] == "comp") and e["build_state"] in ("failed", "no_video"):
                out.append(f"{t['name']} {e['game_date']}: {e['pitcher_name']}'s pitches {'could not be found' if e['build_state'] == 'no_video' else 'failed to build'}. Find a comp or retry.")
            elif (t["adapter"] in BUILDABLE or e["content_kind"] == "comp") and e["game_date"] <= (dt.date.fromisoformat(r["day"]) + dt.timedelta(days=1)).isoformat() and content_state(c, e["id"]) != "ready":
                out.append(f"{t['name']} {e['game_date']}: {e['pitcher_name']}'s pitches are not ready ({e['build_state'] or 'not built'}).")
    return out
