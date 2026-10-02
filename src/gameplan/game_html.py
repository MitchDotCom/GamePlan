"""Single-file HTML for the full-game viewer (see game.py). No external dependencies; data is embedded JSON.

Views: Game (innings grid, plate appearances, pitch by pitch against the plan in force), Pregame board (every count, time
through the order, approach styles), Hitters (swing profile, development targets, this game), Decision log (saved on this
device, exportable). Colors: blue / red diverging pair around gray for swing-better / take-better, always with a letter."""
from __future__ import annotations

import json
import pathlib

VIEWER = pathlib.Path(__file__).parent / "viewer"


def render_app() -> str:
    """The shell for the local server: no game embedded; the page loads the library and games from the API."""
    return render(None)


def render(game: dict | None) -> str:
    """The viewer is three real files (viewer.html, viewer.css, viewer.js) so design checks can read them; this inlines them
    with the game data into one self-contained page."""
    page = (VIEWER / "viewer.html").read_text(encoding="utf-8")
    css = (VIEWER / "viewer.css").read_text(encoding="utf-8")
    js = (VIEWER / "viewer.js").read_text(encoding="utf-8").replace("__DATA__", json.dumps(game, separators=(",", ":")) if game is not None else "null")
    return page.replace("/*__CSS__*/", css).replace("/*__JS__*/", js)


def render_bundle(games: list[dict], artifact: bool = False) -> str:
    """One self-contained page holding several built games, with the library and every control working (builds are the only
    thing it cannot do). Used for the shared preview. artifact=True drops the document tags a hosted page adds itself."""
    import re
    page = render({"bundle": games})
    if artifact:
        page = re.sub(r"<!doctype html>\s*<html[^>]*><head>.*?<title>[^<]*</title>", "<title>GamePlan Preview</title>", page, count=1, flags=re.S)
        page = page.replace("</head><body>", "").replace("</body></html>", "")
    return page
