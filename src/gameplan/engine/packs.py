"""Packs as immutable, hashed content. A pack is built once (by gameplan.prepare) and registered under the sha256 of its manifest and clip bytes; phones fetch by hash and every answer cites the hash,
so an answer always points at exactly what the hitter was shown. Registering the same content again returns the same hash and changes nothing."""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil

from . import db

HASH_LEN = 64


def _sha_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(pack: dict, kind: str, side: str, src_dir: pathlib.Path | None, team_id: int | None = None, practice: bool = False) -> tuple:
    """-> (hash, {file name: sha256}). Everything that shapes what a hitter sees or how it is scored goes into the hash, including WHICH TEAM it was built for:
    identical content for two teams is two packs, so one team's pack can never stand in for, or be changed by, another's."""
    files = {}
    for it in pack["items"]:
        if it.get("file"):
            files[it["file"]] = _sha_file(pathlib.Path(src_dir) / pack["dir"] / it["file"])
    body = dict(kind=kind, side=side, team_id=team_id, practice=bool(practice), mode=pack["mode"], title=pack["title"], subtitle=pack.get("subtitle"),
                items=[dict(id=i["id"], file=i.get("file"), release=i.get("release"), sim=i.get("sim"), keys=i.get("keys"), arsenal=i.get("arsenal"), camera=i.get("camera"), meta=i.get("meta")) for i in pack["items"]],
                files=files)
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest(), files


def register(c, pack: dict, kind: str, side: str, adapter: str, content_root: pathlib.Path, src_dir: pathlib.Path | None = None, team_id: int | None = None, starter_id: int | None = None,
             private_keys: dict | None = None, gate_report: dict | None = None, practice: bool = False) -> str:
    """Store a built pack. `private_keys` maps '<pack id>/<item id>' to {strike, pitch_type} (assessment items carry no key in the pack itself). Returns the hash."""
    h, files = content_hash(pack, kind, side, src_dir, team_id, practice)
    if c.execute("SELECT 1 FROM packs WHERE hash=?", (h,)).fetchone():
        return h
    dest = pathlib.Path(content_root) / h
    tmp = pathlib.Path(content_root) / f".{h}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for name in files:
        shutil.copyfile(pathlib.Path(src_dir) / pack["dir"] / name, tmp / name)
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)                                   # files are in place before the database row exists
    items = []
    for it in pack["items"]:
        it = dict(it)
        items.append(it)
    manifest = dict(id=h, dir=h, title=pack["title"], subtitle=pack.get("subtitle"), mode=pack["mode"], kind=kind, side=side, items=items)
    camera = next((i.get("camera") for i in items if i.get("camera")), "broadcast")
    with db.tx(c):
        c.execute("INSERT INTO packs(hash, team_id, starter_id, kind, side, mode, adapter, camera, title, subtitle, manifest_json, gate_report_json, built_at, practice) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (h, team_id, starter_id, kind, side, pack["mode"], adapter, camera, pack["title"], pack.get("subtitle"), json.dumps(manifest, default=str), json.dumps(gate_report or {}, default=str), db.now(), 1 if practice else 0))
        for it in items:
            k = it.get("keys") or (private_keys or {}).get(f"{pack['id']}/{it['id']}")
            if k is None:
                raise ValueError(f"item {it['id']} has no answer key; refusing to register")
            c.execute("INSERT INTO item_keys(pack_hash, item_id, strike, pitch_type) VALUES (?,?,?,?)", (h, it["id"], None if k.get("strike") is None else int(bool(k["strike"])), k.get("pitch_type")))
        db.audit(c, "system", None, "pack_registered", dict(hash=h, kind=kind, side=side, items=len(items), team_id=team_id))
    return h


def player_manifest(row) -> dict:
    """The manifest a hitter receives: assessment items carry no keys."""
    m = json.loads(row["manifest_json"])
    if m["mode"] == "assess":
        for it in m["items"]:
            it["keys"] = None
    return m


def retire(c, hash_: str, actor: int | None = None) -> None:
    with db.tx(c):
        c.execute("UPDATE packs SET status='retired' WHERE hash=?", (hash_,))
        db.audit(c, "staff", actor, "pack_retired", dict(hash=hash_))
