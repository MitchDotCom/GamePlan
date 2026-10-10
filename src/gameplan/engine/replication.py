"""Is Litestream really replicating? Reads its local metrics so /healthz/deep can say no instead of trusting that a background process is fine.

Healthy means: the metrics answer, no new sync errors since the last look, and the sync counter moved since the last look (Litestream syncs about once a second even when idle).
"""
from __future__ import annotations

import os
import re
import time
import urllib.request

_last = {"sync": None, "errors": None, "at": None}


def enabled() -> bool:
    return bool(os.environ.get("LITESTREAM_METRICS"))


def _metrics(addr: str, timeout: float = 2.0) -> str:
    return urllib.request.urlopen(f"http://{addr}/metrics", timeout=timeout).read().decode()


def _sum(text: str, name: str) -> float:
    return sum(float(m.group(1)) for m in re.finditer(rf"^{name}\{{[^}}]*\}}\s+([0-9.eE+-]+)$", text, re.M))


def check(fetch=_metrics, now=time.time, state=_last) -> list[str]:
    """-> list of problems (empty when replication is healthy or not configured)."""
    if not enabled():
        return []
    try:
        text = fetch(os.environ["LITESTREAM_METRICS"])
    except Exception as e:
        return [f"replication is not running ({type(e).__name__})"]
    sync, errs = _sum(text, "litestream_sync_count"), _sum(text, "litestream_sync_error_count")
    problems = []
    if state["errors"] is not None and errs > state["errors"]:
        problems.append("replication reported new errors")
    if state["sync"] is not None and now() - state["at"] >= 30 and sync <= state["sync"]:
        problems.append("replication has stopped syncing")
    if state["at"] is None or now() - state["at"] >= 30 or problems:
        state.update(sync=sync, errors=errs, at=now())
    return problems
