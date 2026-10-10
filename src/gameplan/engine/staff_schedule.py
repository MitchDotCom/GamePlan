"""Staff pages for the weekly slate: the grid, holds for rain and early finishes, the preview of what every hitter will see, and the comparison-pitcher finder.
Admins change things; a coach can look at their own teams. Everything else (login, CSRF, scoping) comes from staff.register."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re

from fastapi import Request
from fastapi.responses import RedirectResponse
import urllib.parse

from . import comps, db, identity, pitchimport, schedule

TEMPLATES = {
    "schedule": """{% extends "base" %}{% block body %}<h1>Schedule</h1>
<p class="mut">The opposing starter for each affiliate's game. Hitters see the next game's starter; the view flips at {{ rollover }} local, right after the game. Nothing here is guessed: an empty box means hitters see practice pitches and are told so.</p>
<p><a href="/staff/schedule/preview">Preview what every hitter will see</a> · <a href="/staff/starters">MLB schedule suggestions</a></p>
<h2>Showing hitters right now</h2>
<table><tr><th>Affiliate</th><th>Showing</th><th>Starter</th><th>Switches</th>{% if admin %}<th>Rain delay or early finish</th>{% endif %}</tr>
{% for n in now_rows %}<tr><td>{{ n.team }}</td><td>{{ n.day_label }}{% if n.hold %} <b class="bad">held</b>{% endif %}</td>
<td>{% if n.games %}{% for g in n.games %}{{ g.starter }}{% if g.opponent %} vs {{ g.opponent }}{% endif %}{% if g.comp %} <small>(comp: {{ g.comp }})</small>{% endif %}{% if not loop.last %}<br>{% endif %}{% endfor %}{% else %}<span class="bad">nothing confirmed</span>{% endif %}</td>
<td>{{ n.until }}{% if n.hold and n.hold.reason %}<br><small>{{ n.hold.reason }}</small>{% endif %}</td>
{% if admin %}<td><details><summary>change</summary>
<form method="post" action="/staff/schedule/hold" class="row"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="team_id" value="{{ n.team_id }}">Keep this starter until <input type="datetime-local" name="until" required> <input name="reason" placeholder="why (optional)" size="18"><button>Hold</button></form>
<form method="post" action="/staff/schedule/advance" class="inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="team_id" value="{{ n.team_id }}"><button>Show the next game now</button></form>
{% if n.hold %}<form method="post" action="/staff/schedule/clearhold" class="inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="team_id" value="{{ n.team_id }}"><button>Back to the clock</button></form>{% endif %}
</details></td>{% endif %}</tr>{% endfor %}</table>
<h2>Week of {{ dates[0].label }}</h2>
<p><a href="/staff/schedule?start={{ prev }}">&larr; earlier</a> · <a href="/staff/schedule?start={{ today }}">today</a> · <a href="/staff/schedule?start={{ nxt }}">later &rarr;</a></p>
{% if errors %}<div class="card bad"><b>Nothing was saved.</b><ul>{% for e in errors %}<li>{{ e }}</li>{% endfor %}</ul></div>{% endif %}
<form method="post" action="/staff/schedule/save"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="start" value="{{ start }}">
<table><tr><th>Affiliate</th>{% for d in dates %}<th>{{ d.label }}</th>{% endfor %}</tr>
{% for r in rows %}<tr><td><b>{{ r.team.name }}</b><br><small>{{ r.team.level }}</small></td>
{% for d in dates %}<td style="min-width:150px">
{% for g in (1, 2) %}{% set e = r.cells[d.iso] | selectattr('game_no','equalto',g) | list | first | default(none) %}{% set key = r.team.id ~ '|' ~ d.iso ~ '|' ~ g %}
{% set show = g == 1 or e or posted.get('n_' ~ key) %}
{% if show or admin %}{% if not show %}<details><summary><small>+ doubleheader</small></summary>{% endif %}
<div class="cell" style="text-align:left;margin-bottom:4px;{% if e and e.status != 'confirmed' %}border:1px dashed var(--copper){% endif %}">
{% if g == 2 %}<small>game 2</small><br>{% endif %}
<input name="n_{{ key }}" placeholder="Starter" value="{{ posted.get('n_' ~ key, e.pitcher_name if e and e.pitcher_name else '') }}" size="14" {% if not admin %}readonly{% endif %}>
<input name="i_{{ key }}" placeholder="Player id" value="{{ posted.get('i_' ~ key, e.pitcher_id if e and e.pitcher_id else '') }}" size="9" inputmode="numeric" {% if not admin %}readonly{% endif %}>
<input name="o_{{ key }}" placeholder="Opponent" value="{{ posted.get('o_' ~ key, e.opponent if e and e.opponent else '') }}" size="14" {% if not admin %}readonly{% endif %}>
{% if e and e.status == 'confirmed' %}<br><small class="{{ e.chip_class }}">{{ e.chip }}</small>{% if e.link %} <a href="{{ e.link }}">{{ e.link_text }}</a>{% endif %}
{% if admin and e.build_state in ('failed','no_video') %}<form class="inline" method="post" action="/staff/starters/retry"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="starter_id" value="{{ e.id }}"><button>retry</button></form>{% endif %}
{% if admin %} <label><input type="checkbox" name="x_{{ key }}" value="1"> clear</label>{% endif %}
{% elif e %}<br><small>suggested by the MLB schedule: save to confirm</small>{% endif %}
</div>{% if not show %}</details>{% endif %}{% endif %}{% endfor %}
</td>{% endfor %}</tr>{% endfor %}</table>
{% if admin %}<p><button class="pri">Save the week</button> <small class="mut">Saves every box at once or none. A box you leave unchanged stays as it is and is not rebuilt.</small></p>{% endif %}
</form>
<p class="mut">Player ids are MLBAM ids. Pitches are built from the id, so a starter without one will show practice pitches.</p>{% endblock %}""",
    "preview": """{% extends "base" %}{% block body %}<h1>Preview</h1>
<p class="mut">What every active hitter would be shown, computed by the same code the phones use. <a href="/staff/schedule/preview?when=now">Right now</a> · <a href="/staff/schedule/preview?when=next">After the next switch</a>. Showing: <b>{{ when_label }}</b>. <a href="/staff/schedule">Back to the schedule</a></p>
{% for t in teams %}<div class="card"><h2 style="margin-top:0">{{ t.team.name }} <small>{{ t.day }}</small></h2>
<p>{% if t.entries %}{% for e in t.entries %}{{ e.pitcher_name }}{% if e.opponent %} vs {{ e.opponent }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}{% else %}<span class="bad">no starter confirmed</span>{% endif %}</p>
{% if t.problems %}<ul>{% for p in t.problems %}<li class="bad">{{ p }}</li>{% endfor %}</ul>{% else %}<p class="good">All {{ t.hitters|length }} hitters will see the starter's pitches.</p>{% endif %}
<details><summary>{{ t.hitters|length }} hitters</summary><table><tr><th>Hitter</th><th>Bats</th><th>Sees</th></tr>{% for h in t.hitters %}<tr><td>{{ h.name }}</td><td>{{ h.bats }}</td><td class="{{ 'good' if h.kind=='starter' else 'bad' }}">{{ {'starter':'starter pitches','practice':'practice pitches','nothing':'nothing'}[h.kind] }}</td></tr>{% endfor %}</table></details></div>{% endfor %}{% endblock %}""",
    "pitchimport": """{% extends "base" %}{% block body %}<h1>Upload his pitches</h1>
<p><b>{{ s.pitcher_name }}</b> for {{ s.team_name }}, game {{ s.game_date }}{% if s.opponent %} vs {{ s.opponent }}{% endif %}. <a href="/staff/schedule">Back to the schedule</a> · <a href="/staff/comps?starter_id={{ s.id }}">find a comp instead</a></p>
{% if current %}<div class="card good">On file for player {{ s.pitcher_id }}: <b>{{ current.summary.accepted }}</b> drawable pitches from {{ current.summary.starts }} start(s), uploaded {{ current.uploaded_at[:16].replace('T',' ') }} UTC. Uploading again replaces them.</div>{% endif %}
<div class="card"><p>Export this pitcher's pitch-level rows (his last three to six starts, one pitcher per file). Each row needs the pitch type, speed, plate location, batter side and the pitcher's hand, and either the nine path numbers or the release height, release side, extension and the horizontal and induced vertical break. Each pitch is drawn from its own tracking; rows whose numbers do not hold together are left out and counted.</p>
<form method="post" action="/staff/import/preview"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="starter_id" value="{{ s.id }}">
<p><input type="file" id="pf" accept=".csv,.txt,text/csv"></p>
<textarea name="csv" id="pt" rows="6" cols="90" placeholder="or paste the CSV here">{{ posted.get('csv','') }}</textarea>
<p>Plate side is positive toward <select name="plate_sign"><option value="1">the catcher's right, first base (usual)</option><option value="-1" {{ 'selected' if posted.get('plate_sign')=='-1' }}>the catcher's left, third base</option></select> <button class="pri">Check the file</button></p></form></div>
<script>document.getElementById("pf").onchange=function(e){var f=e.target.files[0];if(!f)return;var r=new FileReader();r.onload=function(){document.getElementById("pt").value=r.result};r.readAsText(f)}</script>
{% if error %}<div class="card bad">{{ error }}</div>{% endif %}
{% if res %}<h2>What the file contains</h2>
<p>{{ res.summary.accepted }} of {{ res.summary.total }} rows can be drawn. {{ res.summary.hand }}-handed. Paths: {{ res.summary.path }}.{% if res.summary.hb_direction %} Horizontal break direction: {{ res.summary.hb_direction }} (set from his arm-side and glove-side pitches).{% endif %} {{ in_zone }}% of the pitches are in the strike zone.</p>
<table><tr><th>Pitch</th><th>Count</th><th>Usage</th><th>Velocity</th></tr>{% for t, v in res.summary.types.items() %}<tr><td>{{ t }}</td><td>{{ v.n }}</td><td>{{ '%.0f' % (v.usage*100) }}%</td><td>{{ v.velo }}</td></tr>{% endfor %}</table>
{% for w in res.warnings %}<p class="bad">{{ w }}</p>{% endfor %}
{% if res.rejected %}<p class="mut">Left out: {% for w, n in res.rejected.items() %}{{ n }} {{ w }}{% if not loop.last %}; {% endif %}{% endfor %}.</p>{% endif %}
{% if admin %}<form method="post" action="/staff/import/save"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="starter_id" value="{{ s.id }}"><input type="hidden" name="plate_sign" value="{{ posted.get('plate_sign','1') }}"><textarea name="csv" hidden>{{ posted.get('csv','') }}</textarea>
<input name="note" placeholder="note (where it came from)" size="40"> <button class="pri">Use these pitches</button> <small class="mut">His games on the schedule rebuild from them.</small></form>{% endif %}{% endif %}{% endblock %}""",
    "comps": """{% extends "base" %}{% block body %}<h1>Find a comparison pitcher</h1>
<p><b>{{ s.pitcher_name }}</b> for {{ s.team_name }}, game {{ s.game_date }}{% if s.opponent %} vs {{ s.opponent }}{% endif %}. Pitches: <b>{{ s.build_state or 'not built' }}</b>{% if s.build_detail %} <small>({{ s.build_detail }})</small>{% endif %}.
{% if s.content_kind == 'comp' %}<br>Using a comp now: <b>{{ s.comp_note }}</b>.{% if admin %} <form class="inline" method="post" action="/staff/comps/clear"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="starter_id" value="{{ s.id }}"><button>Go back to his own pitches</button></form>{% endif %}{% endif %}
 <a href="/staff/schedule">Back to the schedule</a></p>
<div class="card"><p>Hitters are told when they are seeing a comp. Pick one only when the starter's own video or tracking cannot be had. Two ways to describe him:</p>
<form method="post" action="/staff/comps/search"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="starter_id" value="{{ s.id }}">
<h2>1. Paste his arsenal export</h2><p class="mut">A CSV with a header row, one row per pitch (Statcast or TrackMan column names work: pitch type, speed, throwing hand, release height and side, extension, arm angle, horizontal and induced vertical break).</p>
<textarea name="csv" rows="5" cols="90" placeholder="paste here">{{ posted.get('csv','') }}</textarea>
<h2>2. Or type what you know</h2>
<div class="row">Hand <select name="hand"><option value="">pick</option><option value="R" {{ 'selected' if posted.get('hand')=='R' }}>Right</option><option value="L" {{ 'selected' if posted.get('hand')=='L' }}>Left</option></select>
Release height ft <input name="rel_z" size="5" value="{{ posted.get('rel_z','') }}"> Release side ft <input name="rel_x" size="5" value="{{ posted.get('rel_x','') }}"> Extension ft <input name="ext" size="5" value="{{ posted.get('ext','') }}"> Arm angle deg <input name="arm_angle" size="5" value="{{ posted.get('arm_angle','') }}"></div>
<table><tr><th>Pitch</th><th>Usage %</th><th>Velo</th><th>Horizontal break in</th><th>Induced vertical break in</th></tr>
{% for i in range(1,7) %}<tr><td><input name="t{{ i }}" size="4" placeholder="FF" value="{{ posted.get('t'~i,'') }}"></td><td><input name="u{{ i }}" size="4" value="{{ posted.get('u'~i,'') }}"></td><td><input name="v{{ i }}" size="5" value="{{ posted.get('v'~i,'') }}"></td><td><input name="h{{ i }}" size="5" value="{{ posted.get('h'~i,'') }}"></td><td><input name="i{{ i }}" size="5" value="{{ posted.get('i'~i,'') }}"></td></tr>{% endfor %}</table>
<label><input type="checkbox" name="any_hand" value="1"> allow the other hand</label> <button class="pri">Find comps</button></form></div>
{% if error %}<div class="card bad">{{ error }}</div>{% endif %}
{% if results %}<h2>Closest MLB pitchers ({{ pool_season }})</h2>{% for w in warnings %}<p class="bad">{{ w }}</p>{% endfor %}
<p class="mut">Score: lower is closer. Gaps are comp minus him. The arm block is release height, side, extension and arm angle in standard deviations of MLB pitchers; the arsenal block weighs each of his pitches by how often he throws it.</p>
<table><tr><th>Pitcher</th><th>Score</th><th>Arm</th><th>Arsenal</th><th>Gaps (comp minus him)</th><th></th></tr>
{% for r in results %}<tr><td>{{ r.name }}<br><small>{{ r.hand }}HP · {{ r.id }} · {{ r.starts }} starts</small></td><td>{{ '%.2f' % r.total }}</td><td>{{ '%.2f' % r.arm }}</td><td>{{ '%.2f' % r.arsenal }}</td>
<td><small>{% for k, v in r.arm_diffs.items() %}{{ k.replace('_',' ') }} {{ '%+.1f' % v }}; {% endfor %}<br>{% for p in r.pitches %}{{ p.type }}: {% if p.missing %}he has none{% else %}{% for k, v in p.diffs.items() %}{{ k }} {{ '%+.1f' % v }} {% endfor %}{% endif %}; {% endfor %}{% if r.extra_usage %}<br>also throws {{ '%.0f' % (r.extra_usage*100) }}% other pitches{% endif %}</small></td>
<td>{% if admin %}<form method="post" action="/staff/comps/use"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="starter_id" value="{{ s.id }}"><input type="hidden" name="comp_id" value="{{ r.id }}"><input type="hidden" name="profile" value="{{ profile_json }}"><button>Use {{ r.name.split(' ')[-1] }}</button></form>{% endif %}</td></tr>{% endfor %}</table>{% endif %}{% endblock %}""",
}


def register(app, ctx, h) -> None:
    current, render, post, scope, teams_in_scope, back = h["current"], h["render"], h["post"], h["scope"], h["teams_in_scope"], h["back"]

    def need_admin(st):
        if st["role"] != "admin":
            raise identity.EngineError("Only an admin can change the schedule.", 403)

    def day_label(iso: str) -> str:
        d = dt.date.fromisoformat(iso)
        return f"{d.strftime('%a')} {d.month}/{d.day}"

    def local_text(c, team_id, iso_utc: str) -> str:
        tz, _ = schedule.clock(c, team_id)
        t = schedule.parse_utc(iso_utc).astimezone(tz)
        return t.strftime("%a ") + str(int(t.strftime("%I"))) + t.strftime(":%M %p ") + (t.tzname() or "")

    def chip(c, e, adapter):
        """-> (text, css class, link, link text) for one confirmed game's content."""
        sid = e["id"]
        if e["content_kind"] == "comp":
            lead = f"comp: {e['comp_note']}; "
        else:
            lead = ""
        bs, st = e["build_state"], schedule.content_state(c, sid)
        link = (f"/staff/import?starter_id={sid}", "upload his pitches or find a comp")
        if e["pitcher_id"] is None:
            return "needs a player id", "bad", None, None
        if adapter not in schedule.BUILDABLE and e["content_kind"] != "comp":
            return "no pitch source: practice pitches", "bad", *link
        if bs == "ready" and st == "ready":
            return lead + "ready", "good", (f"/staff/comps?starter_id={sid}", "change") if e["content_kind"] == "comp" else None, None
        if bs == "ready":
            return lead + f"{st} (one side missing)", "bad", None, None
        if bs in ("queued", "building"):
            return lead + ("queued to build" if bs == "queued" else "building..."), "mut", None, None
        if bs == "no_video":
            return "no video or tracking found", "bad", *link
        if bs == "failed":
            return "build failed: " + (e["build_detail"] or ""), "bad", f"/staff/starters", "see details"
        return "not built", "bad", None, None

    def page_data(c, st, start):
        teams = teams_in_scope(c, st)
        ids = [t["id"] for t in teams]
        wk = schedule.week(c, ids, start, 7)
        for r in wk["rows"]:
            for d, es in r["cells"].items():
                for e in es:
                    if e["status"] == "confirmed":
                        e["chip"], e["chip_class"], e["link"], e["link_text"] = chip(c, e, r["team"]["adapter"])
        now = db.now()
        now_rows = []
        for t in teams:
            r = schedule.resolve(c, t["id"], now)
            now_rows.append(dict(team=t["name"], team_id=t["id"], day_label=day_label(r["day"]), hold=r["hold"], until=local_text(c, t["id"], r["valid_until"]),
                                 games=[dict(starter=e["pitcher_name"], opponent=e["opponent"], comp=e["comp_note"] if e["content_kind"] == "comp" else None) for e in r["entries"]]))
        d0 = dt.date.fromisoformat(start)
        return dict(dates=[dict(iso=d, label=day_label(d)) for d in wk["dates"]], rows=wk["rows"], now_rows=now_rows, start=start, prev=(d0 - dt.timedelta(days=7)).isoformat(), nxt=(d0 + dt.timedelta(days=7)).isoformat(),
                    today=db.local_today(), admin=st["role"] == "admin", rollover=f"{schedule.DEFAULT_HOUR - 12}:00 pm Pacific")

    @app.get("/staff/schedule")
    def schedule_page(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            start = request.query_params.get("start") or db.local_today()
            schedule._date(start)
            return render(request, c, "schedule", "Schedule", errors=[], posted={}, **page_data(c, st, start))
        finally:
            c.close()

    @app.post("/staff/schedule/save")
    async def schedule_save(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            start = f.get("start") or db.local_today()
            schedule._date(start)
            ok_teams = {t["id"]: t["name"] for t in teams_in_scope(c, st)}
            cells = {}
            for k in f:
                m = re.fullmatch(r"([nioxy])_(\d+)\|(\d{4}-\d{2}-\d{2})\|(\d)", k)
                if m:
                    cells.setdefault((int(m.group(2)), m.group(3), int(m.group(4))), {})[m.group(1)] = f[k].strip()
            edits = []
            for (tid, d, g), v in sorted(cells.items()):
                if tid not in ok_teams:
                    raise identity.EngineError("Not your team.", 403)
                clear = "x" in v
                if clear or v.get("n") or v.get("i") or v.get("o"):
                    edits.append(dict(team_id=tid, team_name=ok_teams[tid], game_date=d, game_no=g, name=v.get("n", ""), id=v.get("i", ""), opp=v.get("o", ""), clear=clear))
            res = schedule.apply_grid(c, edits, st["id"])
            if res["errors"]:
                return render(request, c, "schedule", "Schedule", status=400, errors=res["errors"], posted=f, **page_data(c, st, start))
            msg = f"Saved {res['saved']}, unchanged {res['unchanged']}, cleared {res['cancelled']}." + ("".join(" Note: " + w for w in res["warnings"][:4]))
            return RedirectResponse("/staff/schedule?" + urllib.parse.urlencode({"start": start, "m": msg[:600]}), 303)
        finally:
            c.close()

    def team_for(c, st, f):
        tid = int(f.get("team_id") or 0)
        if tid not in {t["id"] for t in teams_in_scope(c, st)}:
            raise identity.EngineError("Not your team.", 403)
        return tid

    @app.post("/staff/schedule/hold")
    async def schedule_hold(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            tid = team_for(c, st, f)
            schedule.hold_current_day(c, tid, f.get("until", ""), f.get("reason", ""), st["id"])
            return back("/staff/schedule", "Held. It ends by itself at the time you set.")
        finally:
            c.close()

    @app.post("/staff/schedule/advance")
    async def schedule_advance(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            day = schedule.advance(c, team_for(c, st, f), st["id"])
            return back("/staff/schedule", f"Hitters now see the {day_label(day)} game.")
        finally:
            c.close()

    @app.post("/staff/schedule/clearhold")
    async def schedule_clear(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            schedule.clear_hold(c, team_for(c, st, f), st["id"])
            return back("/staff/schedule", "Back on the clock.")
        finally:
            c.close()

    @app.get("/staff/schedule/preview")
    def schedule_preview(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            ids = [t["id"] for t in teams_in_scope(c, st)]
            nxt = request.query_params.get("when") == "next"
            out = schedule.preview(c, ids, None, at_next=nxt)
            return render(request, c, "preview", "Preview", teams=out, when_label="after the next switch" if nxt else "right now")
        finally:
            c.close()

    # ------------------------------------------------------------------ comps
    def starter_row(c, st, sid):
        s = c.execute("SELECT s.*, t.name team_name FROM starters s JOIN teams t ON t.id=s.team_id WHERE s.id=? AND s.status='confirmed'", (sid,)).fetchone()
        if s is None or s["team_id"] not in {t["id"] for t in teams_in_scope(c, st)}:
            raise identity.EngineError("No such game.", 404)
        return s

    def comps_page(request, c, st, s, **kw):
        pool = comps.load_pool()
        return render(request, c, "comps", "Comps", s=s, admin=st["role"] == "admin", posted=kw.pop("posted", {}), results=kw.pop("results", None), error=kw.pop("error", None), warnings=kw.pop("warnings", []),
                      profile_json=kw.pop("profile_json", ""), pool_season=pool["season"], **kw)

    @app.get("/staff/comps")
    def comps_get(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            return comps_page(request, c, st, starter_row(c, st, int(request.query_params.get("starter_id") or 0)))
        finally:
            c.close()

    @app.post("/staff/comps/search")
    async def comps_search(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            s = starter_row(c, st, int(f.get("starter_id") or 0))
            try:
                text = (f.get("csv") or "").strip()
                if len(text) > 2_000_000:
                    raise ValueError("That file is too large to paste.")
                prof = comps.profile_from_rows(list(csv.DictReader(io.StringIO(text)))) if text else comps.profile_from_form(f)
                res = comps.rank(prof, n=8, same_hand=not f.get("any_hand"), exclude_ids={s["pitcher_id"]} if s["pitcher_id"] else ())
            except ValueError as e:
                return comps_page(request, c, st, s, posted=f, error=str(e))
            slim = {k: prof[k] for k in ("name", "hand", "rel_z", "rel_x", "ext", "arm_angle", "pitches")}
            return comps_page(request, c, st, s, posted=f, results=res, warnings=prof.get("warnings", []), profile_json=json.dumps(slim, separators=(",", ":")))
        finally:
            c.close()

    @app.post("/staff/comps/use")
    async def comps_use(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            s = starter_row(c, st, int(f.get("starter_id") or 0))
            pool = comps.load_pool()
            comp = next((p for p in pool["pitchers"] if str(p["id"]) == (f.get("comp_id") or "")), None)
            if comp is None:
                raise identity.EngineError("That pitcher is not in the comparison pool.", 400)
            with db.tx(c):
                schedule._retire_packs(c, s["id"])
                c.execute("UPDATE starters SET content_pitcher_id=?, content_kind='comp', comp_note=?, build_state='queued', build_detail='', build_at=? WHERE id=?", (comp["id"], comp["name"], db.now(), s["id"]))
                db.audit(c, "staff", st["id"], "comp_chosen", dict(starter_id=s["id"], starter=s["pitcher_name"], comp_id=comp["id"], comp=comp["name"], profile=(f.get("profile") or "")[:4000]))
            return back("/staff/schedule", f"Using {comp['name']} as the comp for {s['pitcher_name']}. Pitches are queued to build.")
        finally:
            c.close()

    @app.post("/staff/comps/clear")
    async def comps_clear(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            s = starter_row(c, st, int(f.get("starter_id") or 0))
            with db.tx(c):
                schedule._retire_packs(c, s["id"])
                c.execute("UPDATE starters SET content_pitcher_id=NULL, content_kind='own', comp_note=NULL, build_state=?, build_detail='', build_at=? WHERE id=?", ("queued" if s["pitcher_id"] else "", db.now(), s["id"]))
                db.audit(c, "staff", st["id"], "comp_cleared", dict(starter_id=s["id"]))
            return back("/staff/schedule", "Back to his own pitches. Rebuilding.")
        finally:
            c.close()

    # ------------------------------------------------------------------ his own tracking, uploaded
    def import_page(request, c, st, s, **kw):
        cur = pitchimport.load(c, s["pitcher_id"]) if s["pitcher_id"] else None
        return render(request, c, "pitchimport", "Upload pitches", s=s, admin=st["role"] == "admin", current=cur, posted=kw.pop("posted", {}), error=kw.pop("error", None), res=kw.pop("res", None), in_zone=kw.pop("in_zone", 0), **kw)

    @app.get("/staff/import")
    def import_get(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, _, _ = current(request, c)
            return import_page(request, c, st, starter_row(c, st, int(request.query_params.get("starter_id") or 0)))
        finally:
            c.close()

    def parse_form(f):
        return pitchimport.parse(f.get("csv") or "", -1 if f.get("plate_sign") == "-1" else 1)

    @app.post("/staff/import/preview")
    async def import_preview(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            s = starter_row(c, st, int(f.get("starter_id") or 0))
            if not s["pitcher_id"]:
                raise identity.EngineError("This game has no player id yet.", 409)
            res = parse_form(f)
            zone = [r for r in res["rows"] if abs(r["px"]) <= 0.83 and r["sz_bot"] <= r["pz"] <= r["sz_top"]]
            return import_page(request, c, st, s, posted=f, error=res["error"], res=None if res["error"] else res, in_zone=round(100 * len(zone) / max(1, len(res["rows"]))), status=200)
        finally:
            c.close()

    @app.post("/staff/import/save")
    async def import_save(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            s = starter_row(c, st, int(f.get("starter_id") or 0))
            if not s["pitcher_id"]:
                raise identity.EngineError("This game has no player id yet.", 409)
            res = parse_form(f)
            if res["error"]:
                raise identity.EngineError(res["error"], 400)
            n = pitchimport.save(c, s["pitcher_id"], res, st["id"], f.get("note", ""))
            with db.tx(c):
                q = c.execute("UPDATE starters SET build_state='queued', build_detail='', build_at=? WHERE pitcher_id=? AND status='confirmed' AND content_kind='own' AND game_date>=?", (db.now(), s["pitcher_id"], db.plus(db.now(), days=-1)[:10])).rowcount
            return back("/staff/schedule", f"Saved {n} pitches for {s['pitcher_name']}. {q} game(s) queued to build from them.")
        finally:
            c.close()

    @app.post("/staff/starters/retry")
    async def starters_retry(request: Request):
        c = db.connect(ctx.db_path)
        try:
            st, f, _ = await post(request, c)
            need_admin(st)
            s = starter_row(c, st, int(f.get("starter_id") or 0))
            with db.tx(c):
                c.execute("UPDATE starters SET build_state='queued', build_detail='', build_at=? WHERE id=?", (db.now(), s["id"]))
            return back("/staff/schedule", "Queued to build again.")
        finally:
            c.close()
