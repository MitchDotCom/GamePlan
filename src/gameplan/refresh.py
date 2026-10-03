"""Bring every built game up to the current model, then optionally rewrite the shareable preview file.

    python -m gameplan.refresh --league data/league --app-dir data/app --preview /tmp/preview.html

Compares each built game's stamp.txt with version.model_stamp() (a hash of the model code and data files). Only out-of-date games are rebuilt,
two at a time, each in a staging folder that replaces the live game only when it finishes, so the old version stays usable and a killed run just
resumes: rerun the command and it rebuilds what is still out of date. The desktop app does the same from the Library's "Update" button."""
from __future__ import annotations

import argparse
import time

from .server import App


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--app-dir", required=True)
    ap.add_argument("--preview", default=None, help="write the shareable preview HTML here when everything is current")
    a = ap.parse_args(argv)
    app = App(a.league, a.app_dir, None)
    while not app.index_ready:
        time.sleep(1)
    st = app.queue_stale()
    print(f"model {app.stamp}: {st['stale']} game(s) out of date", flush=True)
    last = 0.0
    while True:
        app._pump()
        st = app.refresh_status()
        if not st["queued"] and not st["updating"]:
            break
        if time.time() - last > 30:
            print(f"  updating {', '.join(st['updating']) or '-'}; {st['queued']} queued; {st['stale']} out of date", flush=True)
            last = time.time()
        time.sleep(5)
    left = app.refresh_status()["stale"]
    print(f"done: {left} game(s) still out of date" + (" (their day files may be missing team names or a build failed; see staging logs)" if left else ""), flush=True)
    if a.preview:
        from .preview import main as preview_main
        preview_main(["--app-dir", a.app_dir, "--out", a.preview, "--artifact"])
    return 1 if left else 0


if __name__ == "__main__":
    raise SystemExit(main())
