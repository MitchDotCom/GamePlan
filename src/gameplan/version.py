"""Model stamp: a short hash of the code and data files that decide what a built game contains.

Written next to a game when its build finishes (stamp.txt). A game whose stamp differs from the current one was built by an older model and
is shown as out of date; the server rebuilds those in the background (server.App.queue_stale, or `python -m gameplan.refresh`). Viewer files
are not part of the stamp: the viewer reads the game's JSON at load time, so a UI change never needs a rebuild."""
from __future__ import annotations

import functools
import hashlib
import pathlib

_FILES = ("shape.py", "matchup.py", "decision.py", "plane_term.py", "plane_term_2025.json", "paths.py", "path_variants.py", "pa_value.py",
          "swing_traits.py", "arsenal_fit.py", "mockup.py", "game.py", "opportunity.py", "zone.py", "coach.py", "constants.py",
          "count_values_2025.json", "baseout_2025.json", "scoreinning_2025.json", "savant.py")


@functools.lru_cache(maxsize=1)
def model_stamp() -> str:
    h = hashlib.sha1()
    base = pathlib.Path(__file__).parent
    for name in _FILES:
        p = base / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]
