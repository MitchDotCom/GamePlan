"""Staff pages: roster and claim links, recovery codes, device control, starter confirmation and pack builds, level settings, hitter pocket maps and leaderboards, export, audit.

Server-rendered HTML, one login (a staff token, kept in an HttpOnly SameSite=Strict cookie), a CSRF field on every form, and every query scoped to the teams the staff member may see.
A coach never sees another team's hitters: the check is in the data functions, not in the page.
"""
from __future__ import annotations

import csv
import io
import json
import os
import threading
import urllib.parse

import jinja2
import segno
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .. import app_server as _csvsafe
from . import consent as CONSENT
from . import staff_schedule
from . import analytics, answers as A, db, identity, jobs, packs, playlist, reconcile, runner, schedule, security

PAGE_CSS = """
:root{--bg:#fff;--ink:#1c1030;--ink2:#4a3d63;--line:#e4d8d0;--mid:#f3effa;--purple:#5f249f;--copper:#8f654d;--teal:#005f61;--bad:#a32424}
@media (prefers-color-scheme:dark){:root{--bg:#150b24;--ink:#f4eefb;--ink2:#cfc2e4;--line:#3b2a57;--mid:#2a1a45;--purple:#a678e8;--copper:#c79a80;--teal:#3fc2c0;--bad:#ff8a8a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace}
header{border-top:4px solid var(--copper);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
header b{color:var(--purple);font-style:italic;font-size:18px}a{color:var(--purple)}nav a{margin-right:12px;color:var(--ink2);text-decoration:none}nav a:hover{color:var(--purple)}
main{max-width:1100px;margin:0 auto;padding:16px}h1{color:var(--purple);font-size:22px;margin:0 0 10px}h2{color:var(--purple);font-size:16px;margin:22px 0 6px}
table{border-collapse:collapse;width:100%;margin:6px 0 14px}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--ink2);font-weight:600}
.n{text-align:right}.mut{color:var(--ink2)}.bad{color:var(--bad)}.good{color:var(--teal)}.card{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:10px 0}
button,input,select,textarea{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:5px 10px}button{cursor:pointer}button.pri{background:var(--purple);color:#fff;border:0}
.flash{background:var(--mid);border-radius:8px;padding:8px 12px;margin:8px 0}.code{font-size:28px;letter-spacing:.12em;font-weight:700;background:var(--mid);padding:10px 16px;border-radius:10px;display:inline-block}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;max-width:420px}.cell{padding:8px;border-radius:8px;text-align:center;font-size:12px;background:var(--mid)}.cell b{font-size:16px;display:block}
form.inline{display:inline}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}small{color:var(--ink2)}
@media (max-width:640px){table{display:block;overflow-x:auto}}
"""

TEMPLATES = {
    "base": """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} - Recognition engine</title><style>{{ css|safe }}</style></head><body>
<header><b>Recognition engine</b>{% if staff %}<nav><a href="/staff">Today</a><a href="/staff/roster">Roster</a><a href="/staff/schedule">Schedule</a><a href="/staff/starters">Starters</a><a href="/staff/packs">Packs</a><a href="/staff/leaderboard">Leaderboard</a><a href="/staff/settings">Settings</a>{% if staff['role']=='admin' %}<a href="/staff/admin">Admin</a><a href="/staff/audit">Audit</a>{% endif %}</nav>
<span class="mut">{{ staff['name'] }} ({{ staff['role'] }})</span><form class="inline" method="post" action="/staff/logout"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Sign out</button></form>{% endif %}</header>
<main>{% if flash %}<div class="flash">{{ flash }}</div>{% endif %}{% block body %}{% endblock %}</main></body></html>""",
    "login": """{% extends "base" %}{% block body %}<h1>Staff sign in</h1><form method="post" action="/staff/login" class="card"><p>Paste your staff token.</p><input type="password" name="token" autocomplete="current-password" size="50" required><p><button class="pri">Sign in</button></p></form>{% endblock %}""",
    "dashboard": """{% extends "base" %}{% block body %}<h1>Today</h1>
<div class="row"><div class="card">Hitters<br><b>{{ n_players }}</b></div><div class="card">Active (7 days)<br><b>{{ n_active }}</b></div><div class="card">Answers (7 days)<br><b>{{ n_answers }}</b></div></div>
<h2>Needs attention</h2>{% if findings %}<table><tr><th>Hitter</th><th>What</th><th>What to do</th></tr>{% for f in findings %}<tr><td><a href="/staff/player/{{ f.player_id }}">{{ f.player }}</a></td><td>{{ f.kind.replace('_',' ') }}</td><td>{{ f.detail }}</td></tr>{% endfor %}</table>{% else %}<p class="good">Nothing needs attention.</p>{% endif %}
<h2>Schedule</h2>{% if sched %}<ul>{% for m in sched %}<li class="bad">{{ m }}</li>{% endfor %}</ul><p><a href="/staff/schedule">Open the schedule</a></p>{% else %}<p class="good">Every affiliate has its next starter confirmed and built.</p>{% endif %}
<h2>Next opponent starters</h2>{% if starters %}<table><tr><th>Team</th><th>Game date</th><th>Starter</th><th>Status</th></tr>{% for s in starters %}<tr><td>{{ s.team_name }}</td><td>{{ s.game_date }}</td><td>{{ s.pitcher_name or 'not listed' }}</td><td class="{{ 'good' if s.status=='confirmed' else 'bad' }}">{{ s.status }}</td></tr>{% endfor %}</table><p><a href="/staff/starters">Confirm starters</a></p>{% else %}<p class="mut">No starters yet. <a href="/staff/starters">Add one</a>.</p>{% endif %}
<h2>Background jobs</h2><table><tr><th>Job</th><th>Last ok</th><th>Last run</th></tr>{% for j in jobs %}<tr><td>{{ j.name }}</td><td>{{ j.ok_at or 'never' }}</td><td class="{{ 'good' if j.last_ok else 'bad' }}">{{ j.last_at or 'never' }}{% if j.last_ok==0 %} (failed){% endif %}</td></tr>{% endfor %}</table>{% endblock %}""",
    "roster": """{% extends "base" %}{% block body %}<h1>Roster</h1>
<table><tr><th>Hitter</th><th>Bats</th><th>Team</th><th>Phones</th><th>Agreed</th><th>Last answer</th><th class="n">7 days</th><th></th></tr>
{% for p in players %}<tr><td><a href="/staff/player/{{ p.id }}">{{ p.name }}</a><br><small>{{ p.org_id or '' }}</small></td><td>{{ p.bats }}</td><td>{{ p.team or 'none' }}{% if p.level %} ({{ p.level }}){% endif %}</td><td>{{ p.creds }}</td><td>{{ p.consent }}</td><td>{{ (p.last or '')[:16] }}</td><td class="n">{{ p.n7 }}</td>
<td><form class="inline" method="post" action="/staff/player/{{ p.id }}/claim"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Claim link</button></form>
<form class="inline" method="post" action="/staff/player/{{ p.id }}/recovery"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Recovery code</button></form>
<form class="inline" method="post" action="/staff/player/{{ p.id }}/guest"><input type="hidden" name="csrf" value="{{ csrf }}"><button>iPad code</button></form></td></tr>{% endfor %}</table>
<h2>Add a hitter</h2><form method="post" action="/staff/roster/add" class="card row"><input type="hidden" name="csrf" value="{{ csrf }}"><input name="name" placeholder="Name" required><select name="bats"><option>R</option><option>L</option><option>S</option></select>
<select name="team_id">{% for t in teams %}<option value="{{ t.id }}">{{ t.name }}</option>{% endfor %}</select><input name="org_id" placeholder="Org player id"><button class="pri">Add</button></form>
<h2>Import a roster (CSV)</h2><form method="post" action="/staff/roster/import" class="card"><input type="hidden" name="csrf" value="{{ csrf }}"><p class="mut">Columns: name, bats, team, org_id (players are matched on org_id, never on name), mlbam_id, throws.</p><textarea name="csv" rows="6" cols="80" placeholder="name,bats,team,org_id"></textarea><p><button class="pri">Import</button></p></form>{% endblock %}""",
    "secret": """{% extends "base" %}{% block body %}<h1>{{ heading }}</h1><div class="card">{{ blurb }}{% if url %}<p><b>{{ url }}</b></p><div>{{ qr|safe }}</div>{% endif %}{% if code %}<p><span class="code">{{ code }}</span></p>{% endif %}<p class="mut">{{ note }}</p></div><p><a href="/staff/roster">Back to the roster</a></p>{% endblock %}""",
    "player": """{% extends "base" %}{% block body %}<h1>{{ p.name }}</h1><p class="mut">{{ p.team or 'no team' }}{% if p.level %} ({{ p.level }}){% endif %}, bats {{ p.bats }}{% if p.org_id %}, {{ p.org_id }}{% endif %}</p>
<h2>Phones</h2>{% if creds %}<table><tr><th>Device</th><th>Set up</th><th>Last seen</th><th>Status</th><th></th></tr>{% for k in creds %}<tr><td>{{ k.label }} <small>({{ k.via }})</small></td><td>{{ k.created_at[:16] }}</td><td>{{ (k.last_seen_at or '')[:16] }}</td><td class="{{ 'bad' if k.revoked_at else 'good' }}">{{ ('revoked: ' ~ k.revoked_reason) if k.revoked_at else 'active' }}</td>
<td>{% if not k.revoked_at %}<form class="inline" method="post" action="/staff/credential/{{ k.id }}/revoke"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Remove</button></form>{% endif %}</td></tr>{% endfor %}</table>{% else %}<p class="mut">No phone set up.</p>{% endif %}
{% if staff and staff['role']=='admin' %}<h2>Delete this hitter's data</h2><form method="post" action="/staff/player/{{ p.id }}/delete" class="card row"><input type="hidden" name="csrf" value="{{ csrf }}"><input name="confirm" placeholder="Type his full name to confirm" required><button class="bad">Delete everything</button></form><p class="mut">Removes his answers, devices and agreements permanently. Backups taken before today still hold them until they age out.</p>{% endif %}
{% if not views %}<p class="mut">No answers yet.</p>{% endif %}
{% for v in views %}<h2>{{ v.mode_label }}, {{ v.camera }}</h2><p>Strike or ball: <b>{{ v.sb }}</b> &nbsp; Edge pitches (within 3 in of the zone edge): <b>{{ v.edge }}</b> &nbsp; Which pitch: <b>{{ v.pt }}</b> &nbsp; <small>{{ v.rt }}</small></p>
<p class="mut">Where he recognizes strike or ball, as the batter sees it (in = toward his body). Cells under {{ min_cell }} answers are not shown.</p>
<div class="grid">{% for c in v.cells %}<div class="cell" style="{{ c.style }}">{{ c.name }}{% if c.shown %}<b>{{ c.pct }}</b>n={{ c.n }}<br><small>{{ c.ci }}</small>{% else %}<br>n={{ c.n }}<br><small>too few</small>{% endif %}</div>{% endfor %}</div>
{% if v.recall %}<h2>Which pitch, by thrown type</h2><table><tr><th>Thrown</th><th class="n">n</th><th class="n">Right</th><th>95% interval</th></tr>{% for r in v.recall %}<tr><td>{{ r.name }}</td><td class="n">{{ r.n }}</td><td class="n">{{ r.pct }}</td><td>{{ r.ci }}</td></tr>{% endfor %}</table>{% endif %}
{% if v.conf %}<p class="mut">What he named instead: {% for a,b,n in v.conf %}{{ a }} as {{ b }} ({{ n }}){% if not loop.last %}, {% endif %}{% endfor %}</p>{% endif %}
{% if v.trend %}<table><tr><th>Month</th><th class="n">Strike or ball</th><th class="n">Which pitch</th></tr>{% for t in v.trend %}<tr><td>{{ t.month }}</td><td class="n">{{ t.zone }}</td><td class="n">{{ t.pitch }}</td></tr>{% endfor %}</table>{% endif %}{% endfor %}{% endblock %}""",
    "starters": """{% extends "base" %}{% block body %}<h1>Opponent starters</h1><p class="mut">The schedule only suggests. Nothing is built until a person confirms the starter. A pitcher's MLBAM id is needed to build.</p>
{% for t in teams %}<div class="card"><h2>{{ t.name }} ({{ t.level }}) <small>source: {{ t.adapter }}</small></h2>
<table><tr><th>Game date</th><th>Starter</th><th>MLBAM id</th><th>Status</th><th>Source</th><th></th></tr>{% for s in t.starters %}<tr><td>{{ s.game_date }}</td><td>{{ s.pitcher_name or 'not listed' }}</td><td>{{ s.pitcher_id or '' }}</td><td class="{{ 'good' if s.status=='confirmed' else 'mut' }}">{{ s.status }}</td><td>{{ s.source }}</td>
<td>{% if s.status=='suggested' %}<form class="inline" method="post" action="/staff/starters/confirm"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="team_id" value="{{ t.id }}"><input type="hidden" name="game_date" value="{{ s.game_date }}"><input type="hidden" name="pitcher_id" value="{{ s.pitcher_id or '' }}"><input type="hidden" name="pitcher_name" value="{{ s.pitcher_name or '' }}"><button class="pri">Confirm</button></form>{% endif %}
{% if s.status=='confirmed' and t.adapter!='none' and s.pitcher_id %}<form class="inline" method="post" action="/staff/starters/build"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="starter_id" value="{{ s.id }}"><button>Build packs</button></form>{% endif %}{% if s.build %} <small>{{ s.build }}</small>{% endif %}</td></tr>{% endfor %}</table>
<form method="post" action="/staff/starters/confirm" class="row"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="team_id" value="{{ t.id }}"><input type="date" name="game_date" required><input name="pitcher_name" placeholder="Starter name" required><input name="pitcher_id" placeholder="MLBAM id" size="10"><button class="pri">Confirm a starter</button></form>
{% if t.mlb_team_id %}<form method="post" action="/staff/starters/check" class="inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="team_id" value="{{ t.id }}"><button>Check the schedule now</button></form>{% endif %}</div>{% endfor %}{% endblock %}""",
    "packs": """{% extends "base" %}{% block body %}<h1>Packs</h1><table><tr><th>Title</th><th>Kind</th><th>Side</th><th>Mode</th><th>Source</th><th>Camera</th><th class="n">Pitches</th><th>Team</th><th>Built</th><th>Status</th><th></th></tr>
{% for k in packs %}<tr><td>{{ k.title }}{% if k.practice %} <small>(practice)</small>{% endif %}<br><small>{{ k.hash[:12] }}</small></td><td>{{ k.kind }}</td><td>{{ k.side }}</td><td>{{ k.mode }}</td><td>{{ k.adapter }}</td><td>{{ k.camera }}</td><td class="n">{{ k.n }}</td><td>{{ k.team or 'any (practice)' }}</td><td>{{ k.built_at[:16] }}</td><td class="{{ 'good' if k.status=='active' else 'mut' }}">{{ k.status }}</td>
<td>{% if k.status=='active' %}<form class="inline" method="post" action="/staff/packs/{{ k.hash }}/retire"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Retire</button></form>{% endif %}</td></tr>{% endfor %}</table>{% endblock %}""",
    "settings": """{% extends "base" %}{% block body %}<h1>Level settings</h1><p class="mut">Set here, applied on every phone for that team. Hitters cannot change them.</p>
{% for t in teams %}<form method="post" action="/staff/settings" class="card"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="team_id" value="{{ t.id }}"><h2>{{ t.name }} ({{ t.level }})</h2>
<div class="row"><label>Pause after release (ms) <input name="pause_ms" type="number" min="0" max="400" value="{{ t.s.pause_ms }}" size="5"></label>
<label>View for drawn pitches <select name="view"><option value="hitter_eye" {{ 'selected' if t.s.view=='hitter_eye' }}>Hitter's eye (up to 250 ms)</option><option value="low_home" {{ 'selected' if t.s.view=='low_home' }}>Low behind home</option></select></label>
<label>Daily pitches <input name="daily_cap" type="number" min="1" max="200" value="{{ t.s.daily_cap }}" size="5"></label>
<label>Questions <select name="ask"><option value="both" {{ 'selected' if t.s.ask=='both' }}>Strike or ball, then which pitch</option><option value="zone" {{ 'selected' if t.s.ask=='zone' }}>Strike or ball only</option><option value="pitch" {{ 'selected' if t.s.ask=='pitch' }}>Which pitch only</option></select></label>
<label>Show the rest after answering <select name="reveal"><option value="1" {{ 'selected' if t.s.reveal }}>Yes</option><option value="0" {{ 'selected' if not t.s.reveal }}>No</option></select></label>
<label>Assessment every (days) <input name="assess_every_days" type="number" min="1" max="365" value="{{ t.s.assess_every_days }}" size="5"></label><button class="pri">Save</button></div></form>{% endfor %}{% endblock %}""",
    "leaderboard": """{% extends "base" %}{% block body %}<h1>Leaderboard</h1>
<form method="get" class="row"><select name="team_id"><option value="">All my teams</option>{% for t in teams %}<option value="{{ t.id }}" {{ 'selected' if sel==t.id }}>{{ t.name }}</option>{% endfor %}</select>
<select name="mode"><option value="assess" {{ 'selected' if mode=='assess' }}>Assessment answers (ranked)</option><option value="train" {{ 'selected' if mode=='train' }}>Training answers (not comparable)</option></select><button>Show</button> <a href="/staff/export.csv{{ '?team_id=' ~ sel if sel }}">Export answers (CSV)</a></form>
<p class="mut">Ranked from {{ min_n }} scored answers. One board per camera type; never mixed. Intervals are 95%. Most hitters will not be distinguishable from the group at these sample sizes, and the board says so. "vs peers" is accuracy minus what other hitters scored on the same pitches. This describes recognition on this test, not game performance.</p>
{% if not boards %}<p class="mut">No answers for this selection yet.</p>{% endif %}
{% for cc, d in boards.items() %}<h2>{{ cc }} <small>({{ d.n_players }} hitters)</small></h2>{% for name, ent in d.leaderboards.items() %}<h3>{{ labels[name] }} <small>group {{ pooled[cc][name] }}</small></h3>
<table><tr><th>#</th><th>Hitter</th><th class="n">n</th><th class="n">Accuracy</th><th>95% interval</th><th class="n">vs peers</th><th>Reading</th></tr>{% for e in ent %}<tr><td>{{ e.rank or '' }}</td><td><a href="/staff/player/{{ e.pid }}">{{ e.player }}</a></td><td class="n">{{ e.n }}</td><td class="n">{{ e.acc }}</td><td>{{ e.ci }}</td><td class="n">{{ e.vp }}</td><td class="{{ 'good' if e.tier.startswith('above') else 'bad' if e.tier.startswith('below') else 'mut' }}">{{ e.tier }}</td></tr>{% endfor %}</table>{% endfor %}{% endfor %}{% endblock %}""",
    "admin": """{% extends "base" %}{% block body %}<h1>Admin</h1><h2>Add a team</h2><form method="post" action="/staff/admin/team" class="card row"><input type="hidden" name="csrf" value="{{ csrf }}"><input name="name" placeholder="Team name" required><input name="level" placeholder="Level (e.g. Single-A)" required>
<input name="mlb_team_id" placeholder="MLB team id" size="8"><input name="sport_id" placeholder="Sport id (1 MLB, 11 AAA, 14 Single-A)" size="8"><select name="adapter"><option>none</option><option>mlb_video</option><option>tracking_drawn</option></select><button class="pri">Add</button></form>
<h2>Add a coach</h2><form method="post" action="/staff/admin/coach" class="card"><input type="hidden" name="csrf" value="{{ csrf }}"><input name="name" placeholder="Coach name" required><p>Teams they can see:</p>{% for t in teams %}<label><input type="checkbox" name="team" value="{{ t.id }}"> {{ t.name }}</label><br>{% endfor %}<p><button class="pri">Create (the token is shown once)</button></p></form>
<h2>Staff</h2><table><tr><th>Name</th><th>Role</th><th>Teams</th><th>Status</th></tr>{% for s in staff_list %}<tr><td>{{ s.name }}</td><td>{{ s.role }}</td><td>{{ s.teams }}</td><td>{{ 'revoked' if s.revoked_at else 'active' }}</td></tr>{% endfor %}</table>{% endblock %}""",
    "audit": """{% extends "base" %}{% block body %}<h1>Audit log</h1><table><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr>{% for a in rows %}<tr><td>{{ a.ts[:19] }}</td><td>{{ a.actor_type }} {{ a.actor_id or '' }}</td><td>{{ a.action }}</td><td><small>{{ a.detail_json }}</small></td></tr>{% endfor %}</table>{% endblock %}""",
}


class _NeedLogin(Exception):
    pass


def _form(body: bytes) -> tuple:
    q = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    return {k: v[0] for k, v in q.items()}, q


PN = {"FF": "Four-seam", "SI": "Sinker", "FC": "Cutter", "SL": "Slider", "ST": "Sweeper", "SV": "Slurve", "CU": "Curveball", "KC": "Knuckle curve", "CH": "Changeup", "FS": "Splitter", "FO": "Forkball", "KN": "Knuckleball"}


def _pct(x):
    return "" if x is None else f"{x:.0%}"


def _ci(ci):
    return "" if not ci else f"{ci[0]:.0%} to {ci[1]:.0%}"


def register(app, ctx) -> None:
    env = jinja2.Environment(loader=jinja2.DictLoader({**TEMPLATES, **staff_schedule.TEMPLATES}), autoescape=True)
    get_conn = app.state.get_conn
    builds: dict = {}

    def public_url(request: Request) -> str:
        return (os.environ.get("PUBLIC_URL") or str(request.base_url)).rstrip("/")

    def csrf_for(token: str) -> str:
        return security.keyed_hash(ctx.secret, "csrf:" + token)[:32]

    def current(request: Request, c):
        h = request.headers.get("authorization", "")
        tok = h[7:].strip() if h.lower().startswith("bearer ") else request.cookies.get("staff")
        st = identity.authenticate_staff(c, ctx.secret, tok)
        if st is None:
            raise _NeedLogin()
        return st, tok, not (h.lower().startswith("bearer "))

    def render(request, c, name, title="", status=200, **kw):
        st = tok = None
        try:
            st, tok, _ = current(request, c)
        except _NeedLogin:
            pass
        flash = request.query_params.get("m")
        return HTMLResponse(env.get_template(name).render(css=PAGE_CSS, title=title or name.title(), staff=st, csrf=csrf_for(tok) if tok else "", flash=flash, **kw), status_code=status)

    async def post(request: Request, c):
        """-> (staff, form dict, multi-valued form). Checks the CSRF field when the login came from the cookie."""
        st, tok, via_cookie = current(request, c)
        form, multi = _form(await request.body())
        if via_cookie and form.get("csrf") != csrf_for(tok):
            raise identity.EngineError("This page expired. Reload it and try again.", 403, "csrf")
        return st, form, multi

    def scope(c, st):
        return identity.staff_team_ids(c, st)

    def teams_in_scope(c, st):
        ids = scope(c, st)
        rows = c.execute("SELECT * FROM teams WHERE active=1 ORDER BY level, name").fetchall()
        return [t for t in rows if ids is None or t["id"] in ids]

    def player_ok(c, st, pid: int):
        if c.execute("SELECT 1 FROM players WHERE id=?", (pid,)).fetchone() is None or not identity.staff_can_see_player(c, st, pid):
            raise identity.EngineError("No such hitter.", 404)

    def back(path: str, msg: str):
        return RedirectResponse(f"{path}?{urllib.parse.urlencode({'m': msg})}", 303)

    @app.exception_handler(_NeedLogin)
    async def need_login(request: Request, exc):
        if request.url.path.startswith("/staff") and request.method == "GET":
            return RedirectResponse("/staff/login", 303)
        return HTMLResponse("Sign in required.", 401)

    @app.get("/staff/login")
    def login_page(request: Request):
        c = db.connect(ctx.db_path)
        try:
            return render(request, c, "login", "Sign in")
        finally:
            c.close()

    @app.post("/staff/login")
    async def login(request: Request):
        app.state.throttle(request, "staff")
        form, _ = _form(await request.body())
        c = db.connect(ctx.db_path)
        try:
            st = identity.authenticate_staff(c, ctx.secret, form.get("token", "").strip())
            if st is None:
                with db.tx(c):
                    db.audit(c, "system", None, "staff_login_failed", {})
                return HTMLResponse(env.get_template("login").render(css=PAGE_CSS, title="Sign in", staff=None, csrf="", flash="That token is not valid."), status_code=401)
            r = RedirectResponse("/staff", 303)
            secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
            r.set_cookie("staff", form["token"].strip(), httponly=True, samesite="strict", secure=secure, max_age=12 * 3600, path="/")
            with db.tx(c):
                db.audit(c, "staff", st["id"], "staff_login", {})
            return r
        finally:
            c.close()

    @app.post("/staff/logout")
    def logout():
        r = RedirectResponse("/staff/login", 303)
        r.delete_cookie("staff", path="/")
        return r

    # ------------------------------------------------------------------ pages
    @app.get("/staff")
    def dashboard(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            ids = scope(c, st)
            teams = teams_in_scope(c, st)
            tids = [t["id"] for t in teams]
            week = db.plus(db.now(), days=-7)
            q_in = ",".join("?" * len(tids)) or "NULL"
            n_players = c.execute(f"SELECT COUNT(DISTINCT player_id) n FROM assignments WHERE end_date IS NULL AND team_id IN ({q_in})", tids).fetchone()["n"]
            n_ans = c.execute(f"SELECT COUNT(*) n, COUNT(DISTINCT player_id) p FROM answers WHERE server_ts>=? AND team_id IN ({q_in})", [week, *tids]).fetchone()
            starters = c.execute(f"SELECT s.*, t.name team_name FROM starters s JOIN teams t ON t.id=s.team_id WHERE s.status IN ('confirmed','suggested','tbd') AND s.game_date>=? AND s.team_id IN ({q_in}) ORDER BY s.game_date LIMIT 20", [db.local_today(), *tids]).fetchall()
            js = []
            for name in runner.INTERVALS:
                ok = c.execute("SELECT started_at FROM job_runs WHERE name=? AND ok=1 ORDER BY id DESC LIMIT 1", (name,)).fetchone()
                last = c.execute("SELECT started_at, ok FROM job_runs WHERE name=? ORDER BY id DESC LIMIT 1", (name,)).fetchone()
                js.append(dict(name=name, ok_at=(ok["started_at"][:16] if ok else None), last_at=(last["started_at"][:16] if last else None), last_ok=(last["ok"] if last else None)))
            return render(request, c, "dashboard", "Today", n_players=n_players, n_active=n_ans["p"], n_answers=n_ans["n"], findings=reconcile.findings(c, ids if ids is None else tids), starters=starters, jobs=js, sched=schedule.attention(c, ids if ids is None else tids))
        finally:
            c.close()

    cons_cfg = CONSENT.load()

    def consent_label(c, player_id):
        if not cons_cfg:
            return "not required"
        return "yes" if CONSENT.accepted(c, player_id, cons_cfg["version"]) else "waiting"

    @app.get("/staff/roster")
    def roster(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            teams = teams_in_scope(c, st)
            tids = [t["id"] for t in teams]
            week = db.plus(db.now(), days=-7)
            out = []
            for p in c.execute("SELECT * FROM players WHERE active=1 ORDER BY name").fetchall():
                a = identity.current_assignment(c, p["id"])
                if scope(c, st) is not None and not (a and a["team_id"] in tids):
                    continue
                stats = c.execute("SELECT MAX(server_ts) last, SUM(server_ts>=?) n7 FROM answers WHERE player_id=?", (week, p["id"])).fetchone()
                out.append(dict(id=p["id"], name=p["name"], bats=p["bats"], org_id=p["org_id"], team=a["team_name"] if a else None, level=a["level"] if a else None,
                                creds=c.execute("SELECT COUNT(*) n FROM credentials WHERE player_id=? AND revoked_at IS NULL", (p["id"],)).fetchone()["n"], consent=consent_label(c, p["id"]), last=stats["last"], n7=stats["n7"] or 0))
            return render(request, c, "roster", "Roster", players=out, teams=teams)
        finally:
            c.close()

    @app.post("/staff/roster/add")
    async def roster_add(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            tid = int(f.get("team_id") or 0)
            if scope(c, st) is not None and tid not in scope(c, st):
                raise identity.EngineError("You cannot add hitters to that team.", 403)
            identity.add_player(c, f.get("name", ""), f.get("bats", ""), tid, (f.get("org_id") or "").strip() or None, actor=st["id"])
            return back("/staff/roster", "Hitter added.")
        finally:
            c.close()

    @app.post("/staff/roster/import")
    async def roster_import(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            rows = list(csv.DictReader(io.StringIO(f.get("csv", ""))))
            ids = scope(c, st)
            if ids is not None:
                names = {t["name"] for t in c.execute("SELECT name FROM teams WHERE id IN (%s)" % (",".join("?" * len(ids)) or "NULL"), ids)}
                rows = [r for r in rows if (r.get("team") or "").strip() in names]
            res = identity.import_roster(c, rows, st["id"])
            msg = f"Added {res['added']}, updated {res['updated']}." + (f" {len(res['errors'])} rows skipped: " + "; ".join(f"row {e['row']} {e['error']}" for e in res["errors"][:5]) if res["errors"] else "")
            return back("/staff/roster", msg)
        finally:
            c.close()

    @app.post("/staff/player/{pid}/claim")
    async def make_claim(pid: int, request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = await post(request, c)
            player_ok(c, st, pid)
            tok = identity.create_claim(c, ctx.secret, pid, st["id"])
            url = f"{public_url(request)}/c/{tok}"
            name = c.execute("SELECT name FROM players WHERE id=?", (pid,)).fetchone()["name"]
            qr = segno.make(url, error="m").svg_inline(scale=5, dark="#3f1870", border=2)
            return render(request, c, "secret", "Claim link", heading=f"Claim link for {name}", blurb="Send this link or show this code on the hitter's own phone. It works once and expires in 7 days. Making a new link cancels this one.", url=url, qr=qr, note="It is shown only now. Do not post it in a group chat.")
        finally:
            c.close()

    @app.post("/staff/player/{pid}/recovery")
    async def make_recovery(pid: int, request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = await post(request, c)
            player_ok(c, st, pid)
            r = identity.create_recovery(c, ctx.secret, pid, st["id"])
            name = c.execute("SELECT name FROM players WHERE id=?", (pid,)).fetchone()["name"]
            return render(request, c, "secret", "Recovery code", heading=f"Recovery code for {name}", blurb="Give this to the hitter. He enters it on the 'Who are you?' screen. Using it signs out every other phone he had.", code=f"{r['code'][:4]} {r['code'][4:]}", note=f"Works once, for {r['hours']} hours.")
        finally:
            c.close()

    @app.post("/staff/player/{pid}/guest")
    async def make_guest(pid: int, request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = await post(request, c)
            player_ok(c, st, pid)
            r = identity.new_guest_code(c, ctx.secret, pid, None, st["id"])
            name = c.execute("SELECT name FROM players WHERE id=?", (pid,)).fetchone()["name"]
            return render(request, c, "secret", "Shared iPad code", heading=f"Shared iPad code for {name}", blurb="The hitter enters this on the shared iPad's 'Who are you?' screen. His own phone stays signed in.", code=f"{r['pairing_code'][:4]} {r['pairing_code'][4:]}", note=f"Works once, for {r['pairing_minutes']} minutes.")
        finally:
            c.close()

    @app.post("/staff/player/{pid}/delete")
    async def delete_player(pid: int, request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            if st["role"] != "admin":
                raise identity.EngineError("Admins only.", 403)
            row = c.execute("SELECT name FROM players WHERE id=?", (pid,)).fetchone()
            if row is None or (f.get("confirm") or "").strip() != row["name"]:
                raise identity.EngineError("The name you typed does not match. Nothing was deleted.", 400)
            n = identity.delete_player_data(c, pid, st["id"])
            return back("/staff/roster", f"Deleted {n['answers']} answers and everything else for that hitter.")
        finally:
            c.close()

    @app.post("/staff/credential/{cid}/revoke")
    async def revoke(cid: int, request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = await post(request, c)
            row = c.execute("SELECT player_id FROM credentials WHERE id=?", (cid,)).fetchone()
            if row is None:
                raise identity.EngineError("No such phone.", 404)
            player_ok(c, st, row["player_id"])
            identity.revoke_credential(c, cid, st["id"])
            return back(f"/staff/player/{row['player_id']}", "Phone removed.")
        finally:
            c.close()

    @app.get("/staff/player/{pid}")
    def player_page(pid: int, request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            player_ok(c, st, pid)
            p = c.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
            a = identity.current_assignment(c, pid)
            creds = c.execute("SELECT * FROM credentials WHERE player_id=? ORDER BY id DESC", (pid,)).fetchall()
            views = []
            for (mode, cc), led in analytics.player_view(c, pid).items():
                sb, ed, pt = led["strike_ball"], led["edge"], led["pitch_type"]
                fmt = lambda m: "no answers" if not m.get("n") else f"{_pct(m['accuracy'])} (n={m['n']}, {_ci(m['ci'])})"
                cells = []
                for hgt in ("high", "mid", "low"):
                    for side in ("in", "mid", "away"):
                        k = f"{hgt}-{side}"
                        cell = led["by_pocket"].get(k, {})
                        shown = cell.get("accuracy") is not None
                        shade = ""
                        if shown:
                            acc = cell["accuracy"]
                            shade = f"background:rgba({int(200 - 160 * max(0, min(1, (acc - .4) / .6)))},{int(120 + 80 * acc)},{int(200 - 120 * max(0, min(1, (acc - .4) / .6)))},.35)"
                        cells.append(dict(name=k, shown=shown, pct=_pct(cell.get("accuracy")), n=cell.get("n", 0), ci=_ci(cell.get("ci")), style=shade))
                recall = [dict(name=PN.get(k, k), n=v["n"], pct=_pct(v.get("accuracy")), ci=_ci(v.get("ci"))) for k, v in led["recall_by_type"].items() if v.get("accuracy") is not None]
                trend = [dict(month=t["month"], zone=(f"{_pct(t['zone']['accuracy'])} (n={t['zone']['n']})" if "zone" in t else ""), pitch=(f"{_pct(t['pitch']['accuracy'])} (n={t['pitch']['n']})" if "pitch" in t else "")) for t in led["trend"]]
                rt = f"median decision {int(sb['median_rt_ms'])} ms" if sb.get("median_rt_ms") else ""
                views.append(dict(mode_label="Assessment" if mode == "assess" else "Training", camera=cc, sb=fmt(sb) + (f", d' {sb['d_prime']}" if sb.get("d_prime") is not None else ""), edge=fmt(ed), pt=fmt(pt) + (f", chance {_pct(pt.get('chance_baseline'))}" if pt.get("chance_baseline") else ""),
                                  rt=rt, cells=cells, recall=recall, conf=[(PN.get(a, a), PN.get(b, b), n) for a, b, n in led["confusions"]], trend=trend))
            return render(request, c, "player", p["name"], p=dict(name=p["name"], bats=p["bats"], org_id=p["org_id"], team=a["team_name"] if a else None, level=a["level"] if a else None), creds=[dict(r) for r in creds], views=views, min_cell=8)
        finally:
            c.close()

    @app.get("/staff/starters")
    def starters_page(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            out = []
            for t in teams_in_scope(c, st):
                rows = []
                for s in c.execute("SELECT * FROM starters WHERE team_id=? AND status<>'superseded' ORDER BY game_date DESC, id DESC LIMIT 12", (t["id"],)):
                    d = dict(s)
                    d["build"] = builds.get(s["id"], "")
                    rows.append(d)
                out.append(dict(id=t["id"], name=t["name"], level=t["level"], adapter=t["adapter"], mlb_team_id=t["mlb_team_id"], starters=rows))
            return render(request, c, "starters", "Starters", teams=out)
        finally:
            c.close()

    @app.post("/staff/starters/confirm")
    async def starters_confirm(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            tid = int(f.get("team_id") or 0)
            if scope(c, st) is not None and tid not in scope(c, st):
                raise identity.EngineError("Not your team.", 403)
            pid = int(f["pitcher_id"]) if (f.get("pitcher_id") or "").strip().isdigit() else None
            jobs.confirm_starter(c, tid, f.get("game_date", ""), pid, f.get("pitcher_name", ""), st["id"])
            return back("/staff/starters", "Starter confirmed.")
        finally:
            c.close()

    @app.post("/staff/starters/check")
    async def starters_check(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            tid = int(f.get("team_id") or 0)
            if scope(c, st) is not None and tid not in scope(c, st):
                raise identity.EngineError("Not your team.", 403)
            res = runner.suggest_starters(c)
            return back("/staff/starters", f"Checked the schedule: {res['suggested']} suggested, {res['tbd']} not listed yet.")
        finally:
            c.close()

    @app.post("/staff/starters/build")
    async def starters_build(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            sid = int(f.get("starter_id") or 0)
            row = c.execute("SELECT team_id FROM starters WHERE id=?", (sid,)).fetchone()
            if row is None or (scope(c, st) is not None and row["team_id"] not in scope(c, st)):
                raise identity.EngineError("No such starter.", 404)
            if builds.get(sid, "").startswith("building"):
                return back("/staff/starters", "Already building.")
            builds[sid] = "building..."

            def work():
                try:
                    r = runner.build_starter(ctx.db_path, ctx.data_dir, sid)
                    builds[sid] = ("built " + str(len(set(r["hashes"]))) + " packs") if r["ok"] else "not ready: " + "; ".join(f"{g['gate']} {g.get('side') or ''}".strip() for g in r["gates"] if g.get("status") == "FAIL")
                except identity.EngineError as e:
                    builds[sid] = e.message
                except Exception as e:
                    builds[sid] = f"failed: {type(e).__name__}"
            threading.Thread(target=work, daemon=True).start()
            return back("/staff/starters", "Build started. Reload in a few minutes.")
        finally:
            c.close()

    @app.get("/staff/packs")
    def packs_page(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            ids = scope(c, st)
            out = []
            for k in c.execute("SELECT p.*, t.name team FROM packs p LEFT JOIN teams t ON t.id=p.team_id ORDER BY p.built_at DESC LIMIT 200"):
                if ids is not None and (k["team_id"] is None or k["team_id"] not in ids):
                    continue
                d = dict(k)
                d["n"] = len(json.loads(k["manifest_json"])["items"])
                out.append(d)
            return render(request, c, "packs", "Packs", packs=out)
        finally:
            c.close()

    @app.post("/staff/packs/{hash_}/retire")
    async def pack_retire(hash_: str, request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = await post(request, c)
            row = c.execute("SELECT team_id FROM packs WHERE hash=?", (hash_,)).fetchone()
            if row is None or (scope(c, st) is not None and (row["team_id"] is None or row["team_id"] not in scope(c, st))):
                raise identity.EngineError("No such pack.", 404)
            packs.retire(c, hash_, st["id"])
            return back("/staff/packs", "Pack retired. Hitters keep what they already downloaded and their answers still count.")
        finally:
            c.close()

    @app.get("/staff/settings")
    def settings_page(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            return render(request, c, "settings", "Settings", teams=[dict(id=t["id"], name=t["name"], level=t["level"], s=playlist.settings(c, t["id"])) for t in teams_in_scope(c, st)])
        finally:
            c.close()

    @app.post("/staff/settings")
    async def settings_save(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            tid = int(f.get("team_id") or 0)
            if scope(c, st) is not None and tid not in scope(c, st):
                raise identity.EngineError("Not your team.", 403)
            try:
                pause, cap, every = int(f["pause_ms"]), int(f["daily_cap"]), int(f["assess_every_days"])
            except (KeyError, ValueError):
                raise identity.EngineError("Check the numbers.")
            view, ask, reveal = f.get("view"), f.get("ask"), f.get("reveal")
            if not (0 <= pause <= 400) or view not in ("hitter_eye", "low_home") or ask not in ("both", "zone", "pitch") or reveal not in ("0", "1") or not (1 <= cap <= 200) or not (1 <= every <= 365):
                raise identity.EngineError("One of those settings is out of range.")
            if view == "hitter_eye" and pause > 250:
                raise identity.EngineError("The hitter's-eye view stops at 250 ms: later, the ball leaves the picture.")
            with db.tx(c):
                c.execute("UPDATE level_settings SET pause_ms=?, view=?, daily_cap=?, ask=?, reveal=?, assess_every_days=? WHERE team_id=?", (pause, view, cap, ask, int(reveal), every, tid))
                db.audit(c, "staff", st["id"], "settings_changed", dict(team_id=tid, pause_ms=pause, view=view, daily_cap=cap, ask=ask, reveal=reveal, assess_every_days=every))
            return back("/staff/settings", "Saved.")
        finally:
            c.close()

    @app.get("/staff/leaderboard")
    def leaderboard(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            teams = teams_in_scope(c, st)
            tid = request.query_params.get("team_id") or ""
            mode = request.query_params.get("mode") or "assess"
            if mode not in ("assess", "train"):
                mode = "assess"
            ids = [t["id"] for t in teams]
            if tid.isdigit():
                if int(tid) not in ids:
                    raise identity.EngineError("Not your team.", 403)
                ids = [int(tid)]
            from .. import season_ledger as SL
            b = analytics.boards(c, ids, mode)
            pooled, shaped = {}, {}
            for cc, d in b.items():
                pooled[cc] = {k: _pct(v) or "-" for k, v in d["pooled"].items()}
                shaped[cc] = d
                for name, ent in d["leaderboards"].items():
                    for e in ent:
                        e["acc"] = _pct(e["accuracy"])
                        e["ci"] = _ci(e["ci"])
                        e["vp"] = "" if e["vs_peers"] is None else f"{e['vs_peers'] * 100:+.0f} pts"
                        e["pid"] = _pid_from_label(c, e["player"])
            return render(request, c, "leaderboard", "Leaderboard", teams=teams, sel=int(tid) if tid.isdigit() else None, mode=mode, boards=shaped, pooled=pooled, labels=SL.LABELS, min_n=SL.MIN_N)
        finally:
            c.close()

    def _pid_from_label(c, label: str):
        import re
        m = re.search(r"\(#(\d+)\)$", label)
        if m:
            return int(m.group(1))
        r = c.execute("SELECT id FROM players WHERE name=?", (label,)).fetchone()
        return r["id"] if r else 0

    @app.get("/staff/export.csv")
    def export(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            ids = [t["id"] for t in teams_in_scope(c, st)]
            tid = request.query_params.get("team_id") or ""
            if tid.isdigit():
                if int(tid) not in ids:
                    raise identity.EngineError("Not your team.", 403)
                ids = [int(tid)]
            cols = ["id", "player_id", "player", "team_id", "level", "server_ts", "mode", "task", "call", "key", "correct", "rt_ms", "pause_ms", "camera", "view", "pitch_type", "pocket", "px", "pz", "pack_hash", "item_id", "app_version"]
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(cols)
            for r in analytics.rows(c, ids):
                w.writerow([_csvsafe._safe(r.get(k if k != "player_id" else "pid", "")) for k in cols])
            with db.tx(c):
                db.audit(c, "staff", st["id"], "export", dict(teams=ids))
            return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="answers.csv"'})
        finally:
            c.close()

    @app.get("/staff/admin")
    def admin(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            if st["role"] != "admin":
                raise identity.EngineError("Admins only.", 403)
            staff = []
            for s in c.execute("SELECT * FROM staff ORDER BY id"):
                tn = [r["name"] for r in c.execute("SELECT t.name FROM staff_teams x JOIN teams t ON t.id=x.team_id WHERE x.staff_id=?", (s["id"],))]
                staff.append(dict(name=s["name"], role=s["role"], teams=", ".join(tn) if s["role"] == "coach" else "all", revoked_at=s["revoked_at"]))
            return render(request, c, "admin", "Admin", teams=c.execute("SELECT * FROM teams ORDER BY name").fetchall(), staff_list=staff)
        finally:
            c.close()

    @app.post("/staff/admin/team")
    async def admin_team(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            if st["role"] != "admin":
                raise identity.EngineError("Admins only.", 403)
            num = lambda k: int(f[k]) if (f.get(k) or "").strip().isdigit() else None
            if f.get("adapter") not in ("none", "mlb_video", "tracking_drawn"):
                raise identity.EngineError("Unknown source.")
            identity.add_team(c, f.get("name", ""), f.get("level", ""), num("mlb_team_id"), num("sport_id"), f["adapter"])
            return back("/staff/admin", "Team added.")
        except Exception as e:
            if "UNIQUE" in str(e):
                raise identity.EngineError("A team with that name already exists.", 409)
            raise
        finally:
            c.close()

    @app.post("/staff/admin/coach")
    async def admin_coach(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, multi = await post(request, c)
            if st["role"] != "admin":
                raise identity.EngineError("Admins only.", 403)
            tids = [int(x) for x in multi.get("team", []) if x.isdigit()]
            sid, tok = identity.create_staff(c, ctx.secret, f.get("name", "Coach"), "coach", tids, st["id"])
            return render(request, c, "secret", "New coach", heading=f"Staff token for {f.get('name','Coach')}", blurb="This is the only time it is shown. Send it privately. It signs in at /staff/login.", code=None, url=None, note=tok)
        finally:
            c.close()

    @app.get("/staff/audit")
    def audit(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            if st["role"] != "admin":
                raise identity.EngineError("Admins only.", 403)
            return render(request, c, "audit", "Audit", rows=c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 300").fetchall())
        finally:
            c.close()

    staff_schedule.register(app, ctx, dict(current=current, render=render, post=post, scope=scope, teams_in_scope=teams_in_scope, back=back))
