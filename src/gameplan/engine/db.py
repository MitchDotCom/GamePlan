"""SQLite storage for the engine (WAL mode, one file). The SQL is kept portable (TEXT, INTEGER, REAL, ISO-8601 UTC strings, ON CONFLICT upserts) so it can move to Postgres.

Rules: answers are append-only (a correction is a row in `voids`); every credential, claim token and code is stored only as a keyed hash; every identity event writes `audit_log`.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import pathlib
import sqlite3

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS teams (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, level TEXT NOT NULL, mlb_team_id INTEGER, sport_id INTEGER, adapter TEXT NOT NULL DEFAULT 'none', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY, org_id TEXT UNIQUE, mlbam_id INTEGER, name TEXT NOT NULL, bats TEXT NOT NULL CHECK (bats IN ('L','R','S')), throws TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assignments (
  id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id), team_id INTEGER NOT NULL REFERENCES teams(id), start_date TEXT NOT NULL, end_date TEXT);
CREATE INDEX IF NOT EXISTS ix_assign_player ON assignments(player_id, start_date);
CREATE TABLE IF NOT EXISTS claim_tokens (
  id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id), token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, revoked_at TEXT, created_by INTEGER);
CREATE TABLE IF NOT EXISTS credentials (
  id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id), token_hash TEXT NOT NULL UNIQUE, label TEXT, created_at TEXT NOT NULL, last_seen_at TEXT, revoked_at TEXT, revoked_reason TEXT, via TEXT NOT NULL, shared INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_cred_player ON credentials(player_id);
CREATE TABLE IF NOT EXISTS codes (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('pair','recover')), player_id INTEGER NOT NULL REFERENCES players(id), code_hash TEXT NOT NULL UNIQUE,
  from_credential_id INTEGER, created_by INTEGER, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, revoked_at TEXT, keep_issuer INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS staff (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('admin','coach')), token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS staff_teams (staff_id INTEGER NOT NULL REFERENCES staff(id), team_id INTEGER NOT NULL REFERENCES teams(id), PRIMARY KEY (staff_id, team_id));
CREATE TABLE IF NOT EXISTS starters (
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), game_date TEXT NOT NULL, game_pk INTEGER, pitcher_id INTEGER, pitcher_name TEXT,
  status TEXT NOT NULL CHECK (status IN ('suggested','tbd','confirmed','rejected','superseded')), source TEXT NOT NULL, checked_at TEXT, confirmed_by INTEGER, confirmed_at TEXT, season INTEGER);
CREATE INDEX IF NOT EXISTS ix_starters_team ON starters(team_id, game_date);
CREATE TABLE IF NOT EXISTS packs (
  hash TEXT PRIMARY KEY, team_id INTEGER REFERENCES teams(id), starter_id INTEGER REFERENCES starters(id), kind TEXT NOT NULL, side TEXT NOT NULL, mode TEXT NOT NULL CHECK (mode IN ('train','assess')),
  adapter TEXT NOT NULL, camera TEXT NOT NULL, title TEXT NOT NULL, subtitle TEXT, manifest_json TEXT NOT NULL, gate_report_json TEXT, built_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', practice INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS item_keys (pack_hash TEXT NOT NULL REFERENCES packs(hash), item_id TEXT NOT NULL, strike INTEGER, pitch_type TEXT, PRIMARY KEY (pack_hash, item_id));
CREATE TABLE IF NOT EXISTS level_settings (
  team_id INTEGER PRIMARY KEY REFERENCES teams(id), pause_ms INTEGER NOT NULL DEFAULT 150, view TEXT NOT NULL DEFAULT 'hitter_eye', daily_cap INTEGER NOT NULL DEFAULT 30, ask TEXT NOT NULL DEFAULT 'both', reveal INTEGER NOT NULL DEFAULT 1,
  assess_every_days INTEGER NOT NULL DEFAULT 28);
CREATE TABLE IF NOT EXISTS playlists (
  player_id INTEGER NOT NULL REFERENCES players(id), play_date TEXT NOT NULL, side TEXT NOT NULL, pack_hashes_json TEXT NOT NULL, rule_version TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (player_id, play_date, side));
CREATE TABLE IF NOT EXISTS answers (
  id TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id), credential_id INTEGER NOT NULL REFERENCES credentials(id), team_id INTEGER, level TEXT, session TEXT, pack_hash TEXT NOT NULL REFERENCES packs(hash), item_id TEXT NOT NULL,
  task TEXT NOT NULL CHECK (task IN ('zone','pitch')), mode TEXT NOT NULL CHECK (mode IN ('train','assess')), call TEXT NOT NULL, options TEXT, rt_ms INTEGER, pause_ms INTEGER, camera TEXT, view TEXT, q_order INTEGER, clip_trial INTEGER,
  key TEXT, correct INTEGER, client_correct INTEGER, stand TEXT, pitch_type TEXT, family TEXT, pocket TEXT, px REAL, pz REAL, sz_top REAL, sz_bot REAL, speed REAL,
  device_ts TEXT, server_ts TEXT NOT NULL, app_version TEXT, content_version TEXT);
CREATE INDEX IF NOT EXISTS ix_answers_player ON answers(player_id, server_ts);
CREATE INDEX IF NOT EXISTS ix_answers_pack ON answers(pack_hash, item_id, task);
CREATE TABLE IF NOT EXISTS voids (answer_id TEXT PRIMARY KEY REFERENCES answers(id), reason TEXT NOT NULL, staff_id INTEGER, voided_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS heartbeats (
  id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id), credential_id INTEGER, ts TEXT NOT NULL, stored INTEGER, sent INTEGER, unsent INTEGER, oldest_unsent_ts TEXT, app_version TEXT, persisted INTEGER, detail TEXT);
CREATE INDEX IF NOT EXISTS ix_hb_player ON heartbeats(player_id, ts);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id INTEGER, action TEXT NOT NULL, detail_json TEXT);
CREATE TABLE IF NOT EXISTS consents (id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id), credential_id INTEGER, version TEXT NOT NULL, accepted_at TEXT NOT NULL, UNIQUE (player_id, version));
CREATE TABLE IF NOT EXISTS slate_holds (
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), pin_date TEXT NOT NULL, until_utc TEXT NOT NULL, reason TEXT, set_by INTEGER, set_at TEXT NOT NULL, cleared_at TEXT);
CREATE INDEX IF NOT EXISTS ix_holds_team ON slate_holds(team_id, set_at);
CREATE TABLE IF NOT EXISTS job_runs (id INTEGER PRIMARY KEY, name TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, ok INTEGER, detail_json TEXT);
"""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def plus(iso: str, **kw) -> str:
    t = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ") + datetime.timedelta(**kw)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def today() -> str:
    return now()[:10]


def local_today() -> str:
    """The date at the org's home clock (Pacific). Roster dates and the schedule window use this: the UTC date is already tomorrow every evening on the west coast."""
    import zoneinfo
    return datetime.datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles")).date().isoformat()


def connect(path: str | pathlib.Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")        # an acknowledged answer must survive a power cut
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=10000")
    return c


def _add_column(c, table: str, column: str, ddl: str) -> None:
    if column not in [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def migrate(c: sqlite3.Connection) -> None:
    c.executescript(SCHEMA)
    _add_column(c, "credentials", "shared", "INTEGER NOT NULL DEFAULT 0")          # v3: shared-iPad sign-ins
    _add_column(c, "codes", "keep_issuer", "INTEGER NOT NULL DEFAULT 0")
    for col, ddl in (("game_no", "INTEGER NOT NULL DEFAULT 1"), ("opponent", "TEXT"), ("content_pitcher_id", "INTEGER"), ("content_kind", "TEXT NOT NULL DEFAULT 'own'"),
                     ("comp_note", "TEXT"), ("build_state", "TEXT NOT NULL DEFAULT ''"), ("build_detail", "TEXT"), ("build_at", "TEXT")):
        _add_column(c, "starters", col, ddl)                                           # v4: the weekly schedule
    _add_column(c, "level_settings", "rollover_tz", "TEXT NOT NULL DEFAULT 'America/Los_Angeles'")
    _add_column(c, "level_settings", "rollover_hour", "INTEGER NOT NULL DEFAULT 21")
    c.execute("CREATE INDEX IF NOT EXISTS ix_starters_slate ON starters(team_id, game_date, game_no, status)")
    row = c.execute("SELECT MAX(version) v FROM schema_version").fetchone()
    if row["v"] is None or row["v"] < SCHEMA_VERSION:          # v2 added the consents table, which executescript above has just created
        c.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    elif row["v"] > SCHEMA_VERSION:
        raise RuntimeError(f"database is schema {row['v']}, this code knows {SCHEMA_VERSION}: refusing to run")


@contextlib.contextmanager
def tx(c: sqlite3.Connection):
    """One write transaction. BEGIN IMMEDIATE takes the write lock up front so two writers queue instead of failing half way."""
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
    except BaseException:
        c.execute("ROLLBACK")
        raise
    else:
        c.execute("COMMIT")


def audit(c: sqlite3.Connection, actor_type: str, actor_id, action: str, detail: dict | None = None) -> None:
    c.execute("INSERT INTO audit_log(ts, actor_type, actor_id, action, detail_json) VALUES (?,?,?,?,?)", (now(), actor_type, actor_id, action, json.dumps(detail or {}, default=str)))
