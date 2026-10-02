"""Write one shareable page holding every built game in the app folder (library, game pages, all controls except Build).

    python -m gameplan.preview --app-dir data/app --out preview.html [--artifact]
"""
from __future__ import annotations

import argparse
import json
import pathlib

from .game_html import render_bundle


def load_games(app_dir: str) -> list[dict]:
    games = []
    for d in sorted(pathlib.Path(app_dir, "games").iterdir()):
        f = d / "game.json"
        if not f.exists():
            continue
        g = json.loads(f.read_text(encoding="utf-8"))
        boards = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (d / "boards").glob("*.json")} if (d / "boards").exists() else {}
        for side in g["sides"].values():
            side["board"]["hitters"] = [dict(boards[h["id"]], order=h["order"]) if h.get("pending") and h["id"] in boards else h for h in side["board"]["hitters"]]
        if any(h.get("pending") for s in g["sides"].values() for h in s["board"]["hitters"]):
            continue                                        # boards not finished: leave the game out of the preview
        games.append(g)
    games.sort(key=lambda g: (g["date"], str(g["game_pk"])))
    return games


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-dir", default="data/app")
    ap.add_argument("--out", default="preview.html")
    ap.add_argument("--artifact", action="store_true")
    a = ap.parse_args(argv)
    games = load_games(a.app_dir)
    pathlib.Path(a.out).write_text(render_bundle(games, artifact=a.artifact), encoding="utf-8")
    print(f"wrote {a.out} with {len(games)} games: " + ", ".join(f"{g['away']} at {g['home']} {g['date']}" for g in games))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
