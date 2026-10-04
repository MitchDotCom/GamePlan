"""Model stamp: a short hash of the code and data files that decide what a built game contains.

Written next to a game when its build finishes (stamp.txt). A game whose stamp differs from the current one was built by an older model and
is shown as out of date; the server rebuilds those in the background (server.App.queue_stale, or `python -m gameplan.refresh`).

The file list is not hand-kept: it is the import chain of the build entry point (game.py), found by reading import statements, plus every
JSON data file in the package. A new module on the build path changes the stamp automatically. Viewer files are not part of it: the viewer
reads the game's JSON at load time, so a UI change never needs a rebuild."""
from __future__ import annotations

import ast
import functools
import hashlib
import pathlib

ENTRY = "game"


def _closure(base: pathlib.Path) -> list[str]:
    seen, todo = set(), [ENTRY]
    while todo:
        name = todo.pop()
        p = base / f"{name}.py"
        if name in seen or not p.exists():
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                todo += [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
    return sorted(seen)


@functools.lru_cache(maxsize=1)
def model_stamp() -> str:
    h = hashlib.sha1()
    base = pathlib.Path(__file__).parent
    names = [f"{n}.py" for n in _closure(base)] + sorted(p.name for p in base.glob("*.json"))
    for name in names:
        p = base / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]
