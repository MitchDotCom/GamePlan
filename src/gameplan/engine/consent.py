"""Consent: the hitter reads the organization's wording once per version and agrees; nothing is served or stored for him until he has.

The wording lives in config/consent.json (or the file named by ENGINE_CONSENT_FILE). Changing its `version` asks every hitter again. Each agreement is a row (who, which version, when, on which device) and an audit entry; rows are never edited.
"""
from __future__ import annotations

import json
import os
import pathlib

from . import db, identity

DEFAULT = pathlib.Path(__file__).resolve().parents[3] / "config" / "consent.json"


def load(path: str | pathlib.Path | None = None) -> dict | None:
    p = pathlib.Path(path or os.environ.get("ENGINE_CONSENT_FILE") or DEFAULT)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    if not d.get("version") or not isinstance(d.get("paragraphs"), list):
        raise RuntimeError(f"{p}: consent file needs a version and a list of paragraphs")
    return d if d.get("required", True) else None


def public(d: dict) -> dict:
    return {k: d[k] for k in ("version", "title", "paragraphs", "button") if k in d}


def accepted(c, player_id: int, version: str) -> bool:
    return c.execute("SELECT 1 FROM consents WHERE player_id=? AND version=?", (player_id, version)).fetchone() is not None


def accept(c, player: dict, credential: dict, version: str, current: dict) -> None:
    if version != current["version"]:
        raise identity.EngineError("The wording changed. Reload the app and read it again.", 409, "consent_version")
    with db.tx(c):
        if not accepted(c, player["id"], version):
            c.execute("INSERT INTO consents(player_id, credential_id, version, accepted_at) VALUES (?,?,?,?)", (player["id"], credential["id"], version, db.now()))
            db.audit(c, "player", player["id"], "consent.accept", dict(version=version, credential=credential["id"]))
