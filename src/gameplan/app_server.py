"""Reference server for the phone app: serves the app and the content, and collects answers.

  python -m gameplan.app_server --content <dir>/content --data <dir>/data [--port 8080] [--token SECRET] [--keys <dir>/private_keys.json]

  GET  /                      the app (phone_app/)           GET /content/...   queue and clips
  GET  /config.json           {content, sync_url, token}     POST /api/trials   {"trials": [...]}, idempotent by trial id
  GET  /api/trials.csv        every answer, one CSV           GET /api/health
With --keys, rows from assessment packs (shipped with no answer) are scored here: the clip's key is applied and `correct` filled in. The phone never sees those keys.
A phone needs HTTPS for the install and offline features; this server speaks plain HTTP and is for the LAN, tests and local use. Put it (or the static files) behind the org's own HTTPS host.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 5 * 1024 * 1024
APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "phone_app"
COLS = "player,session,mode,ts,pack,clip,clip_trial,task,q_order,ask,pause_ms,call,rt_ms,key,correct,pitch_type,family,pocket,px,pz,sz_top,sz_bot,speed,stand,p_throws,release_frame,id".split(",")


def _safe(v):
    """A spreadsheet runs a text cell that starts with = + - @ tab or CR as a formula. Prefix those so a hostile player name stays text. Plain numbers are left alone."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        try:
            float(v)
            return v
        except ValueError:
            return "'" + v
    return v


class Store:
    def __init__(self, data: pathlib.Path, keys: pathlib.Path | None):
        data.mkdir(parents=True, exist_ok=True)
        self.path = data / "trials.jsonl"
        self.lock = threading.Lock()
        self.keys = json.loads(keys.read_text()) if keys and keys.exists() else {}
        self.ids = set()
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.ids.add(json.loads(line)["id"])

    def add(self, trials: list[dict]) -> int:
        new = 0
        with self.lock, open(self.path, "a") as f:
            for t in trials:
                if not t.get("id") or t["id"] in self.ids:
                    continue
                self.ids.add(t["id"])
                f.write(json.dumps(t) + "\n")
                new += 1
        return new

    def rows(self) -> list[dict]:
        out = [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()] if self.path.exists() else []
        for t in out:
            if t.get("key") in ("", None) and self.keys:
                k = self.keys.get(f"{t.get('pack')}/{t.get('clip')}")
                if k:
                    a = k.get("zone_go" if t.get("task") == "zone" else "pitch_go")
                    if a is not None:
                        t["key"] = "GO" if a else "NO-GO"
                        t["correct"] = int((t["call"] == "GO") == a)
        return out

    def csv(self) -> str:
        b = io.StringIO()
        w = csv.DictWriter(b, COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: _safe(v) for k, v in r.items()} for r in self.rows())
        return b.getvalue()


def make_handler(content: pathlib.Path, store: Store, token: str | None, sync_url: str):
    class H(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            from urllib.parse import unquote
            p = unquote(path.split("?")[0].split("#")[0])
            root, rel = (content, p[len("/content/"):]) if p.startswith("/content/") else (APP_DIR, p.lstrip("/"))
            full = (root / rel).resolve()
            if root.resolve() != full and root.resolve() not in full.parents:       # no path may leave the folder it is served from
                return str(root / "__forbidden__")
            return str(full)

        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/api/health":
                return self._send(200, b'{"ok":true}')
            if p == "/api/trials.csv":
                if token and self.headers.get("X-Token") != token:
                    return self._send(401, b"{}")
                return self._send(200, store.csv().encode(), "text/csv")
            if p == "/config.json":
                return self._send(200, json.dumps(dict(content="content/", sync_url=sync_url, token=token or "")).encode())
            if p in ("", "/"):
                self.path = "/index.html"
            return super().do_GET()

        def do_POST(self):
            if self.path != "/api/trials":
                return self._send(404, b"{}")
            if token and self.headers.get("X-Token") != token:
                return self._send(401, b'{"error":"token"}')
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size > MAX_BODY:
                    return self._send(413, b'{"error":"too large"}')
                body = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(body.get("trials"), list) or not all(isinstance(t, dict) for t in body["trials"]):
                    return self._send(400, b'{"error":"trials must be a list of objects"}')
                n = store.add(body["trials"])
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)[:80]}).encode())
            return self._send(200, json.dumps({"stored": n}).encode())
    return H


def serve(content, data, port=8080, token=None, keys=None):
    store = Store(pathlib.Path(data), pathlib.Path(keys) if keys else None)
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(pathlib.Path(content), store, token, "/api/trials"))
    return srv, store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--token", default=None)
    ap.add_argument("--keys", default=None)
    a = ap.parse_args(argv)
    srv, _ = serve(a.content, a.data, a.port, a.token, a.keys)
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.connect(("10.255.255.255", 1))
            ip = u.getsockname()[0]
    except OSError:
        ip = "your-computer-ip"
    print(f"On this computer: http://localhost:{a.port}")
    print(f"On a phone on the same Wi-Fi: http://{ip}:{a.port}   (plain HTTP: play and sync work; install and offline need HTTPS, see docs/PHONE_TEST.md)")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
