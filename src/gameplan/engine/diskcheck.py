"""Run this on the real host before trusting it: does the data volume behave like a local disk for SQLite?

  python -m gameplan.engine.diskcheck /data

It makes a scratch database inside the folder, then checks: file locks work, WAL mode sticks, several processes writing at once lose nothing, the database survives a hard kill of a writer,
and a durable commit takes a believable time (a network share that ignores fsync looks too fast; a very slow one looks too slow). It deletes its scratch files. Exit 0 means every check passed.
"""
from __future__ import annotations

import fcntl
import multiprocessing as mp
import os
import pathlib
import signal
import sqlite3
import sys
import tempfile
import time


def _writer(path: str, tag: str, n: int, out):
    c = sqlite3.connect(path, timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")
    for i in range(n):
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT INTO t(tag, i) VALUES (?,?)", (tag, i))
        c.execute("COMMIT")
        out.put((tag, i))


def run(folder: str) -> list[tuple[str, bool, str]]:
    results = []

    def check(name, fn):
        try:
            msg = fn()
            results.append((name, True, msg or ""))
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))

    d = pathlib.Path(tempfile.mkdtemp(prefix="diskcheck-", dir=folder))
    db = str(d / "scratch.db")

    def locks():
        with open(d / "lock", "w") as a, open(d / "lock", "w") as b:
            fcntl.flock(a, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                fcntl.flock(b, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return "a second exclusive lock is refused, as it should be"
            raise RuntimeError("two exclusive locks were both granted: the volume does not enforce file locks")

    def wal():
        c = sqlite3.connect(db)
        mode = c.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        c.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, tag TEXT, i INTEGER)")
        c.commit()
        c.close()
        if mode != "wal":
            raise RuntimeError(f"journal mode is {mode}, not wal")
        return "WAL mode accepted"

    def fsync_speed():
        c = sqlite3.connect(db, isolation_level=None)
        c.execute("PRAGMA synchronous=FULL")
        t = time.time()
        for i in range(50):
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO t(tag, i) VALUES ('speed', ?)", (i,))
            c.execute("COMMIT")
        per = (time.time() - t) / 50 * 1000
        c.close()
        if per > 250:
            raise RuntimeError(f"a durable commit takes {per:.0f} ms: too slow for a phone waiting on a reply")
        return f"{per:.1f} ms per durable commit"

    def many_writers():
        q = mp.Queue()
        ps = [mp.Process(target=_writer, args=(db, f"w{k}", 100, q)) for k in range(4)]
        [p.start() for p in ps]
        [p.join(120) for p in ps]
        if any(p.exitcode != 0 for p in ps):
            raise RuntimeError("a writer process failed")
        c = sqlite3.connect(db)
        n = c.execute("SELECT COUNT(*) FROM t WHERE tag LIKE 'w%'").fetchone()[0]
        c.close()                                   # an open reader here would leave a stale view for the next check
        if n != 400:
            raise RuntimeError(f"4 writers x 100 rows should give 400, found {n}")
        return "4 concurrent writers, 400 of 400 rows"

    def hard_kill():
        q = mp.Queue()
        p = mp.Process(target=_writer, args=(db, "kill", 100000, q))
        p.start()
        got = set()
        t = time.time()
        while time.time() - t < 1.5:
            try:
                got.add(q.get(timeout=0.2))
            except Exception:
                pass
        os.kill(p.pid, signal.SIGKILL)
        p.join()
        while True:
            try:
                got.add(q.get_nowait())
            except Exception:
                break
        c = sqlite3.connect(db)
        have = {(r[0], r[1]) for r in c.execute("SELECT tag, i FROM t WHERE tag='kill'")}
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.close()
        if ok != "ok":
            raise RuntimeError("integrity check failed after a hard kill")
        if got - have:
            raise RuntimeError(f"{len(got - have)} acknowledged rows are missing after a hard kill")
        return f"{len(got)} acknowledged rows all present after kill -9"

    for name, fn in (("file locks", locks), ("WAL mode", wal), ("durable commit speed", fsync_speed), ("concurrent writers", many_writers), ("hard kill", hard_kill)):
        check(name, fn)
    for f in d.glob("*"):
        f.unlink()
    d.rmdir()
    return results


def main(argv=None) -> int:
    folder = (argv or sys.argv[1:] or [os.environ.get("ENGINE_DATA", ".")])[0]
    res = run(folder)
    for name, ok, msg in res:
        print(("PASS " if ok else "FAIL ") + name + (": " + msg if msg else ""))
    return 0 if all(ok for _, ok, _ in res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
