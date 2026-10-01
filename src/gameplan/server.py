"""Local GamePlan server: a game library, a page per game, and saved decisions, all behind a small JSON API.

    python -m gameplan.server --league data/league            # then open http://127.0.0.1:8765

The server only listens on this computer. Games are built on demand by the same engine used from the command line
(`python -m gameplan.game`), one process per game, so a long build never blocks the page. Everything it stores lives in
`<app dir>/` (default data/app): built games, the coach decision log, and a small index of the games in the data.

    GET  /                       the app
    GET  /api/games              every game in the data, with build status
    GET  /api/game/<pk>          one built game
    POST /api/build              {"game_pk": "..."}  start building a game
    GET  /api/board/<pk>/<id>    one hitter's pregame board (404 while it is still building)
    GET  /api/build/<pk>         build status and the last lines of its log
    GET  /api/log                saved decisions and skips
    PUT  /api/log                replace them
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import pathlib
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .game_html import render_app, VIEWER

MAX_BUILDS = 2


class App:
    def __init__(self, league: str, app_dir: str, names_csv: str | None):
        self.league = pathlib.Path(league)
        self.dir = pathlib.Path(app_dir)
        self.games_dir = self.dir / "games"
        self.games_dir.mkdir(parents=True, exist_ok=True)
        self.names = self._names(names_csv)
        self.lock = threading.Lock()
        self.index: list[dict] = []
        self.index_ready = False
        self.jobs: dict[str, dict] = {}
        self.import_bundled()
        threading.Thread(target=self.build_index, daemon=True).start()

    # ---- names and index
    @staticmethod
    def _names(path):
        out = {}
        if path and pathlib.Path(path).exists():
            for r in csv.DictReader(open(path, encoding="utf-8-sig")):
                n = r.get("last_name, first_name", "")
                out[r["player_id"]] = (n.split(",")[0].strip() if "," in n else n)
        return out

    def import_bundled(self):
        """Games shipped in docs/gameview* become library entries so the library is never empty."""
        for f in glob.glob(str(pathlib.Path(__file__).resolve().parents[2] / "docs" / "gameview*" / "game.json")):
            try:
                g = json.load(open(f, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            d = self.games_dir / str(g["game_pk"])
            if not (d / "game.json").exists():
                d.mkdir(parents=True, exist_ok=True)
                (d / "game.json").write_text(json.dumps(g, separators=(",", ":")), encoding="utf-8")

    def build_index(self):
        cache = self.dir / "index.json"
        known = json.loads(cache.read_text()) if cache.exists() else {}
        out = []
        for f in sorted(glob.glob(str(self.league / "*.csv"))):
            day = pathlib.Path(f).stem
            st = pathlib.Path(f).stat()
            key = f"{st.st_size}-{int(st.st_mtime)}"
            if known.get(day, {}).get("key") == key:
                games = known[day]["games"]
            else:
                games = self._scan_day(f, day)
                known[day] = {"key": key, "games": games}
            out += games
        cache.write_text(json.dumps(known), encoding="utf-8")
        with self.lock:
            self.index = out
            self.index_ready = True

    @staticmethod
    def _scan_day(path, day):
        games: dict[str, dict] = {}
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rd = csv.reader(fh)
            head = next(rd)
            ix = {c: i for i, c in enumerate(head)}
            need = ("game_pk", "pitcher", "inning_topbot", "at_bat_number")
            if any(c not in ix for c in need):
                return []
            ht, at = ix.get("home_team"), ix.get("away_team")
            for r in rd:
                pk = r[ix["game_pk"]]
                g = games.setdefault(pk, {"game_pk": pk, "date": day, "home": r[ht] if ht is not None else "", "away": r[at] if at is not None else "",
                                          "starters": {}, "pitches": 0, "pas": set()})
                g["pitches"] += 1
                g["pas"].add(r[ix["at_bat_number"]])
                g["starters"].setdefault(r[ix["inning_topbot"]], r[ix["pitcher"]])
        out = []
        for g in games.values():
            g["pas"] = len(g["pas"])
            out.append(g)
        return out

    # ---- status
    def status(self, pk: str) -> str:
        if (self.games_dir / pk / "game.json").exists():
            return "ready"
        j = self.jobs.get(pk)
        if j and j["proc"].poll() is None:
            return "building"
        if j and j["proc"].returncode not in (0, None):
            return "failed"
        return "new"

    def games(self) -> dict:
        with self.lock:
            idx, ready = list(self.index), self.index_ready
        built = {p.name for p in self.games_dir.iterdir() if (p / "game.json").exists()}
        rows = []
        seen = set()
        for g in idx:
            seen.add(g["game_pk"])
            pk0 = g["game_pk"]
            bd = self.games_dir / pk0 / "boards"
            rows.append({**g, "status": self.status(pk0), "boards_running": bool(self.jobs.get(pk0) and self.jobs[pk0]["proc"].poll() is None),
                         "boards_done": len(list(bd.glob("*.json"))) if bd.exists() else 0,
                         "home_starter": self.names.get(g["starters"].get("Top", ""), g["starters"].get("Top", "")),
                         "away_starter": self.names.get(g["starters"].get("Bot", ""), g["starters"].get("Bot", ""))})
        for pk in built - seen:                       # built games whose day file is not in this data folder
            try:
                g = json.load(open(self.games_dir / pk / "game.json", encoding="utf-8"))
            except (OSError, ValueError):
                continue
            rows.append({"game_pk": pk, "date": g["date"], "home": g["home"], "away": g["away"], "pas": len(g["pas"]), "pitches": sum(len(p["pitches"]) for p in g["pas"]),
                         "status": "ready", "home_starter": g["sides"]["Top"]["starter_name"], "away_starter": g["sides"]["Bot"]["starter_name"], "starters": {}})
        rows.sort(key=lambda r: (r["date"], r["game_pk"]), reverse=True)
        return {"ready": ready, "games": rows}

    def start_build(self, pk: str):
        if not re.fullmatch(r"\d+", pk):
            return 400, {"error": "bad game id"}
        if self.status(pk) in ("ready", "building"):
            return 200, {"status": self.status(pk)}
        if sum(1 for j in self.jobs.values() if j["proc"].poll() is None) >= MAX_BUILDS:
            return 429, {"error": f"{MAX_BUILDS} builds are already running; try again when one finishes"}
        g = next((x for x in self.index if x["game_pk"] == pk), None)
        if not g or not g["home"] or not g["away"]:
            return 404, {"error": "game not found, or its day file has no team names"}
        out = self.games_dir / pk
        out.mkdir(parents=True, exist_ok=True)
        log = open(out / "build.log", "w")
        proc = subprocess.Popen([sys.executable, "-u", "-m", "gameplan.game", "--league", str(self.league), "--date", g["date"], "--game", pk,
                                 "--away", g["away"], "--home", g["home"], "--out", str(out),
                                 "--lazy-boards", "--cache-dir", str(self.dir / "cache")], stdout=log, stderr=subprocess.STDOUT)
        self.jobs[pk] = {"proc": proc, "started": time.time()}
        return 200, {"status": "building"}

    def build_status(self, pk: str):
        j = self.jobs.get(pk)
        tail = ""
        lp = self.games_dir / pk / "build.log"
        if lp.exists():
            tail = "\n".join(lp.read_text(errors="ignore").splitlines()[-4:])
        bd = self.games_dir / pk / "boards"
        return {"status": self.status(pk), "elapsed": int(time.time() - j["started"]) if j else 0, "log": tail,
                "boards_done": len(list(bd.glob("*.json"))) if bd.exists() else 0, "running": bool(j and j["proc"].poll() is None)}

    # ---- log
    def get_log(self):
        p = self.dir / "log.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def put_log(self, obj):
        tmp = self.dir / "log.json.tmp"
        tmp.write_text(json.dumps(obj), encoding="utf-8")
        tmp.replace(self.dir / "log.json")


def make_handler(app: App):
    shell = render_app().encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or "json" in ctype else ""))
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                return self._send(200, render_app().encode("utf-8"), "text/html")   # re-render so edits to the viewer files show on refresh
            if path == "/api/games":
                return self._send(200, app.games())
            m = re.fullmatch(r"/api/game/(\d+)", path)
            if m:
                f = app.games_dir / m.group(1) / "game.json"
                return self._send(200, f.read_bytes()) if f.exists() else self._send(404, {"error": "not built"})
            m = re.fullmatch(r"/api/build/(\d+)", path)
            if m:
                return self._send(200, app.build_status(m.group(1)))
            m = re.fullmatch(r"/api/board/(\d+)/(\d+)", path)
            if m:
                f = app.games_dir / m.group(1) / "boards" / f"{m.group(2)}.json"
                return self._send(200, f.read_bytes()) if f.exists() else self._send(404, {"pending": True, **app.build_status(m.group(1))})
            if path == "/api/log":
                return self._send(200, app.get_log())
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/api/build":
                code, body = app.start_build(str(self._body().get("game_pk", "")))
                return self._send(code, body)
            self._send(404, {"error": "not found"})

        def do_PUT(self):
            if self.path == "/api/log":
                app.put_log(self._body())
                return self._send(200, {"ok": True})
            self._send(404, {"error": "not found"})

    return H


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="data/league")
    ap.add_argument("--app-dir", default="data/app")
    ap.add_argument("--names", default="data/pitcher_names_2025.csv")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the app in your browser")
    ap.add_argument("--download", action="store_true", help="first download the 2025 season of pitch data into --league (about 195 files)")
    a = ap.parse_args(argv)
    if a.download:
        from .bulk import fetch_league_days, season_days
        fetch_league_days(season_days("2025-03-18", "2025-09-28"), a.league)
    app = App(a.league, a.app_dir, a.names)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(app))
    print(f"GamePlan running at http://127.0.0.1:{a.port} (Ctrl+C to stop)", flush=True)
    if a.open:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{a.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
