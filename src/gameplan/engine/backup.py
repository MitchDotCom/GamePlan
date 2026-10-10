"""Backups: a consistent copy of the live SQLite file (the online backup API, safe while the service runs), checked by opening it and counting answers, with old copies pruned.
`restore_check` is the drill: open a backup in a clean place and compare its counts with the live database."""
from __future__ import annotations

import pathlib
import sqlite3

from . import db


def backup(live_path: pathlib.Path, dest_dir: pathlib.Path, keep: int = 60) -> pathlib.Path:
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = db.now().replace(":", "").replace("-", "").replace(".", "")[:21]        # to the microsecond: two backups never share a name, so a restore point is never overwritten
    out = dest_dir / f"engine-{stamp}.db"
    src = sqlite3.connect(str(live_path))
    dst = sqlite3.connect(str(out))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    counts(out)                                                   # fails loudly if the copy cannot be read
    for old in sorted(dest_dir.glob("engine-*.db"))[:-keep]:
        old.unlink()
    return out


def counts(path: pathlib.Path) -> dict:
    c = sqlite3.connect(str(path))
    try:
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"integrity check failed: {ok}")
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("players", "answers", "packs", "credentials", "audit_log")}
    finally:
        c.close()


def restore_check(backup_path: pathlib.Path, live_path: pathlib.Path) -> dict:
    """The backup must hold every answer the live database held when the backup was taken or earlier: its counts may be lower than live (newer answers) but never higher, and it must open and pass integrity."""
    b, l = counts(backup_path), counts(live_path)
    return dict(backup=b, live=l, ok=all(b[k] <= l[k] for k in b))


def restore(backup_path: pathlib.Path, live_path: pathlib.Path) -> dict:
    """Put a backup in place of the live database. Stop the service first. The backup is checked before anything is touched, and the old file is kept beside it as engine.db.before-restore."""
    import shutil
    backup_path, live_path = pathlib.Path(backup_path), pathlib.Path(live_path)
    before = counts(backup_path)                                  # raises if it cannot be opened or fails integrity
    tmp = live_path.with_suffix(".restoring")
    shutil.copyfile(backup_path, tmp)
    counts(tmp)
    if live_path.exists():
        shutil.move(str(live_path), str(live_path) + ".before-restore")
    for ext in ("-wal", "-shm"):                                  # leftovers from the old file would be replayed onto the restored one
        p = pathlib.Path(str(live_path) + ext)
        if p.exists():
            p.unlink()
    tmp.rename(live_path)
    return dict(restored=before, kept_old=str(live_path) + ".before-restore")


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="python -m gameplan.engine.backup --restore <backup file> --into /data/engine.db   (service stopped)")
    ap.add_argument("--restore", required=True)
    ap.add_argument("--into", required=True)
    a = ap.parse_args(argv)
    print(json.dumps(restore(a.restore, a.into), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
