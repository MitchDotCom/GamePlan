"""The engine's web service: player API, content, claim and recovery, plus the staff pages (staff.py).

  ENGINE_DATA=/data ENGINE_SECRET=... ENGINE_ADMIN_TOKEN=... uvicorn gameplan.engine.app:app --host 0.0.0.0 --port 8080

Everything a hitter does goes through a device credential (Authorization: Bearer ...). Claim, pairing and recovery are the only unauthenticated writes and are throttled per client address.
"""
from __future__ import annotations

import logging
import os
import pathlib
import re

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import answers as A
from . import db, identity, playlist, security

log = logging.getLogger("engine")
APP_VERSION = "engine-1"
MIN_APP_VERSION = "engine-1"
MAX_BODY = 1_000_000
STATIC = pathlib.Path(__file__).resolve().parents[3] / "phone_app"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
FILE_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


async def read_json(request: Request) -> dict:
    """The request body as a JSON object, or a clean 400 (never a server error)."""
    try:
        body = await request.json()
    except ValueError:
        raise identity.EngineError("The request body must be JSON.", 400, "bad_json")
    if not isinstance(body, dict):
        raise identity.EngineError("The request body must be a JSON object.", 400, "bad_json")
    return body


class Ctx:
    def __init__(self, data_dir: pathlib.Path, secret: str, trust_proxy: bool = False):
        self.data_dir = pathlib.Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "engine.db"
        self.content_root = self.data_dir / "content"
        self.content_root.mkdir(exist_ok=True)
        self.secret = secret
        self.trust_proxy = trust_proxy
        self.public = security.Throttle(20, 60)         # claim, pair, recover, staff sign-in: per client address
        self.public_all = security.Throttle(300, 60)    # the same endpoints, whole service (a spread-out guesser still hits this)
        c = db.connect(self.db_path)
        db.migrate(c)
        c.close()


def client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def create_app(data_dir=None, secret: str | None = None, admin_token: str | None = None, static_dir: pathlib.Path | None = None, trust_proxy: bool | None = None) -> FastAPI:
    data_dir = data_dir or os.environ.get("ENGINE_DATA", "./engine_data")
    secret = secret or os.environ.get("ENGINE_SECRET")
    if not secret or len(secret) < 24:
        raise RuntimeError("ENGINE_SECRET must be set to at least 24 characters (it keys every stored hash; changing it signs everyone out).")
    admin_token = admin_token or os.environ.get("ENGINE_ADMIN_TOKEN")
    trust_proxy = bool(os.environ.get("TRUST_PROXY")) if trust_proxy is None else trust_proxy
    ctx = Ctx(data_dir, secret, trust_proxy)
    app = FastAPI(title="Recognition engine", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    static_dir = pathlib.Path(static_dir or STATIC)

    c0 = db.connect(ctx.db_path)
    try:
        if admin_token and c0.execute("SELECT COUNT(*) n FROM staff").fetchone()["n"] == 0:
            identity.create_staff(c0, secret, "Admin", "admin", token=admin_token)        # first start only: the admin token you chose becomes the first staff login
    finally:
        c0.close()

    def get_conn():
        c = db.connect(ctx.db_path)
        try:
            yield c
        finally:
            c.close()

    def throttle(request: Request, what: str):
        ip = client_ip(request, ctx.trust_proxy)
        if not ctx.public.check(f"{what}:{ip}") or not ctx.public_all.check(what):
            raise identity.EngineError("Too many tries. Wait a minute and try again.", 429, "throttled")

    def player_auth(request: Request, c=Depends(get_conn)):
        h = request.headers.get("authorization", "")
        got = identity.authenticate(c, ctx.secret, h[7:].strip() if h.lower().startswith("bearer ") else None)
        if got is None:
            raise identity.EngineError("You are signed out. Ask a coach for a new link.", 401, "signed_out")
        return got

    app.state.get_conn = get_conn
    app.state.throttle = throttle

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl is None:
                return JSONResponse({"error": "Content-Length is required.", "code": "length_required"}, 411)
            if not cl.isdigit() or int(cl) > MAX_BODY:
                return JSONResponse({"error": "Request too large.", "code": "too_large"}, 413)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"               # claim tokens travel in the page address; never leak them to a font host or anything else
        resp.headers["X-Frame-Options"] = "DENY"
        p = request.url.path
        if p.startswith("/api/") or p.startswith("/c/") or p.startswith("/staff") or p == "/config.json":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(identity.EngineError)
    async def engine_error(request: Request, exc: identity.EngineError):
        return JSONResponse({"error": exc.message, "code": exc.code}, exc.status)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"error": "Something went wrong on our side. Your answers on the phone are safe; try again.", "code": "server_error"}, 500)

    # ------------------------------------------------------------------ public
    @app.get("/healthz")
    def healthz(c=Depends(get_conn)):
        v = c.execute("SELECT MAX(version) v FROM schema_version").fetchone()["v"]
        return dict(ok=True, schema=v, time=db.now(), version=APP_VERSION)

    @app.get("/config.json")
    def config():
        return dict(engine=True, api="/api", content="/content/", app_version=APP_VERSION, min_app_version=MIN_APP_VERSION)

    @app.get("/c/{token}")
    def claim_page(token: str):
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.post("/api/claim/preview")
    async def claim_preview(request: Request, c=Depends(get_conn)):
        throttle(request, "claim")
        body = await read_json(request)
        return identity.claim_preview(c, ctx.secret, str(body.get("token", "")))

    @app.post("/api/claim/confirm")
    async def claim_confirm(request: Request, c=Depends(get_conn)):
        throttle(request, "claim")
        body = await read_json(request)
        return identity.claim_confirm(c, ctx.secret, str(body.get("token", "")), str(body.get("label", "")))

    @app.post("/api/pair")
    async def pair(request: Request, c=Depends(get_conn)):
        throttle(request, "pair")
        body = await read_json(request)
        return identity.pair(c, ctx.secret, str(body.get("code", "")), str(body.get("label", "")))

    @app.post("/api/recover")
    async def recover(request: Request, c=Depends(get_conn)):
        throttle(request, "pair")
        body = await read_json(request)
        return identity.recover(c, ctx.secret, str(body.get("code", "")), str(body.get("label", "")))

    # ------------------------------------------------------------------ player (credential)
    @app.get("/api/me")
    def me(auth=Depends(player_auth), c=Depends(get_conn)):
        cred, player = auth
        card = identity.player_card(c, player["id"])
        st = playlist.settings(c, card["team_id"]) if card["team_id"] else None
        return dict(player=card, settings=st, server_time=db.now(), app_version=APP_VERSION, min_app_version=MIN_APP_VERSION)

    @app.post("/api/signout")
    def signout(auth=Depends(player_auth), c=Depends(get_conn)):
        identity.sign_out(c, auth[0]["id"])
        return dict(ok=True)

    @app.post("/api/pairing-code")
    def pairing_code(auth=Depends(player_auth), c=Depends(get_conn)):
        return identity.new_pairing_code(c, ctx.secret, auth[1]["id"], auth[0]["id"])

    @app.get("/api/playlist")
    def get_playlist(auth=Depends(player_auth), c=Depends(get_conn)):
        out = playlist.compose(c, auth[1])
        out["server_time"] = db.now()
        return out

    @app.post("/api/answers")
    async def post_answers(request: Request, auth=Depends(player_auth), c=Depends(get_conn)):
        body = await read_json(request)
        res = A.ingest(c, auth[1], auth[0], body.get("answers"))
        res["server_time"] = db.now()
        return res

    @app.post("/api/heartbeat")
    async def heartbeat(request: Request, auth=Depends(player_auth), c=Depends(get_conn)):
        b = await read_json(request)
        def n(k):
            try:
                return max(0, min(10 ** 9, int(b.get(k))))
            except (TypeError, ValueError):
                return None
        with db.tx(c):
            c.execute("INSERT INTO heartbeats(player_id, credential_id, ts, stored, sent, unsent, oldest_unsent_ts, app_version, persisted, detail) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (auth[1]["id"], auth[0]["id"], db.now(), n("stored"), n("sent"), n("unsent"), str(b.get("oldest_unsent_ts") or "")[:40] or None, str(b.get("app") or "")[:20], 1 if b.get("persisted") else 0, str(b.get("detail") or "")[:200]))
        return dict(ok=True, server_time=db.now())

    @app.get("/content/{hash_}/{name}")
    def content(hash_: str, name: str, auth=Depends(player_auth)):
        if not HASH_RE.match(hash_) or not FILE_RE.match(name):
            raise identity.EngineError("Not found.", 404)
        f = ctx.content_root / hash_ / name
        if not f.is_file():
            raise identity.EngineError("Not found.", 404)
        return FileResponse(f, media_type="video/mp4" if name.endswith(".mp4") else "application/octet-stream", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    from . import staff
    staff.register(app, ctx)

    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app


def app_factory():
    return create_app()
