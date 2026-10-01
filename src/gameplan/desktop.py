"""GamePlan as a desktop app: the same local server in a native window, no browser.

Data lives in the user's home folder (~/GamePlan), not next to the program, so the app can be installed anywhere:
    ~/GamePlan/data/league   the season's pitch data (downloaded from inside the app)
    ~/GamePlan/data/app      built games, boards and saved decisions

    gameplan-desktop            (or: python -m gameplan.desktop)
"""
from __future__ import annotations

import multiprocessing
import pathlib
import socket
import threading
from http.server import ThreadingHTTPServer

HOME = pathlib.Path.home() / "GamePlan"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(league: pathlib.Path, app_dir: pathlib.Path, names: pathlib.Path | None = None):
    """Start the server on a free port in a background thread. Returns (url, shutdown function)."""
    from .server import App, make_handler

    app = App(str(league), str(app_dir), str(names) if names else None)
    port = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/", srv.shutdown


def main() -> int:
    multiprocessing.freeze_support()                 # needed so builds can start inside a packaged app
    try:
        import webview
    except ImportError:
        raise SystemExit("The desktop window needs pywebview: pip install 'gameplan[desktop]'")
    (HOME / "data").mkdir(parents=True, exist_ok=True)
    url, stop = start_server(HOME / "data" / "league", HOME / "data" / "app", HOME / "data" / "pitcher_names_2025.csv")
    webview.create_window("GamePlan", url, width=1400, height=900, min_size=(1000, 700))
    webview.start()
    stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
