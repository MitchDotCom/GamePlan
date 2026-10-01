"""Single-file HTML for the coach mock-up board (see mockup.py). Data is embedded as JSON; the page has no
external dependencies. Colors follow the dataviz reference palette: a blue / red diverging pair around a gray
midpoint for swing-better / take-better, with letters (G swing, x take, . no call) so color is never the only cue."""
from __future__ import annotations

import json

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GamePlan Lineup Board</title>
<style>
:root{color-scheme:light;--bg:#fcfcfb;--panel:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--line:#e3e2dd;--pos:#2a78d6;--neg:#e34948;--mid:#f0efec;--accent:#2a78d6;--warn:#fab219}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#1a1a19;--panel:#222221;--ink:#ffffff;--ink2:#c3c2b7;--line:#383835;--pos:#3987e5;--neg:#e66767;--mid:#383835;--accent:#3987e5}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#1a1a19;--panel:#222221;--ink:#ffffff;--ink2:#c3c2b7;--line:#383835;--pos:#3987e5;--neg:#e66767;--mid:#383835;--accent:#3987e5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:22px 0 8px}h3{font-size:14px;margin:0 0 6px;color:var(--ink2);font-weight:600}
.banner{background:var(--mid);border-left:4px solid var(--warn);padding:8px 12px;border-radius:4px;margin:10px 0;color:var(--ink2);font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);font-size:14px}th{color:var(--ink2);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
tr.hit{cursor:pointer}tr.hit:hover,tr.hit.sel{background:var(--mid)}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;border:1px solid var(--line);color:var(--ink2)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.counts{display:grid;grid-template-columns:repeat(4,auto);gap:4px;width:max-content}
.styles{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-top:10px}
.grid{display:grid;grid-template-columns:repeat(5,34px);gap:2px;margin:8px 0}
.cell{width:34px;height:30px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;border-radius:3px;background:var(--mid);color:var(--ink2)}
.chip{display:inline-block;margin:0 4px 4px 0;padding:1px 8px;border-radius:10px;background:var(--mid);font-size:12px}
.mut{color:var(--ink2);font-size:13px}.num{font-variant-numeric:tabular-nums}
.axis{font-size:11px;color:var(--ink2)}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
details summary{cursor:pointer;color:var(--ink2)}
.logrow{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px}
select,input[type=text]{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:3px 8px}
.chosen{outline:2px solid var(--accent)}
.note{font-size:12px;color:var(--ink2)}
@media print{.noprint{display:none}body{font-size:12px}.card{break-inside:avoid}}
</style></head><body><div class="wrap">
<h1 id="title"></h1><div class="mut" id="sub"></div>
<div class="banner">Mock-up built from public 2025 MLB data with the current engine, fit only on games before the date. For feedback on format and usefulness. Not validated for Single-A, and the approach styles are illustrative, not the final path generator.</div>
<h2>Starter profile</h2><div class="card" id="starter"></div>
<h2>Lineup</h2><div class="card"><table id="lineup"></table><div class="mut" style="margin-top:6px">Click a hitter. Support = tracked swings before the date (high 800+, medium 300+, thin under 300). Decision value is the post-game result against the plan, in runs; positive is better than the plan's other option.</div></div>
<div id="hitter"></div>
<h2>Questions for the coach</h2>
<div class="card"><ol>
<li>Which of this would you actually use in a pregame meeting, and which would you skip?</li>
<li>Is three styles per count useful, too many, or the wrong three? What would you call them?</li>
<li>Does the "development target" list match what you already see in these hitters?</li>
<li>In the post-game view, which pitches would you want to show the hitter on video?</li>
<li>What is missing (a pitch, a count, a situation, a person's name for something)?</li>
</ol></div>
</div>
<script>
const B = __DATA__;
const $ = (s,r=document)=>r.querySelector(s);
const NX=5, NZ=6;
let H=0, TTO="1", CNT="0-0", PT=null, EXP=false;
let LOG={};try{LOG=JSON.parse(localStorage.getItem("gameplanLog")||"{}")}catch(e){LOG={}}
const saveLog=()=>{try{localStorage.setItem("gameplanLog",JSON.stringify(LOG))}catch(e){}};
const pct=x=>(100*x).toFixed(0)+"%";
const sgn=x=>(x>=0?"+":"")+x.toFixed(2);
function mixColor(delta){const a=Math.min(Math.abs(delta)/0.12,1);const c=delta>=0?"var(--pos)":"var(--neg)";return `color-mix(in srgb, ${c} ${Math.round(20+60*a)}%, var(--mid))`}
$("#title").textContent=`Lineup board vs ${B.starter.name}`;
$("#sub").textContent=`${B.date}. Starter had ${B.starter.starts_before} earlier starts in the data. Model: ${B.model}.`;
(function(){const ar=B.starter.arsenal_tto1_0_0;const rows=Object.entries(ar).sort((a,b)=>b[1].usage-a[1].usage).map(([k,v])=>`<tr><td>${k}</td><td class="num">${pct(v.usage)}</td><td class="num">${v.velo.toFixed(1)}</td><td class="num">${v.ivb.toFixed(1)}</td><td class="num">${v.hb.toFixed(1)}</td></tr>`).join("");
$("#starter").innerHTML=`<table><tr><th>Pitch</th><th>Usage (0-0)</th><th>Velo</th><th>IVB in</th><th>HB in</th></tr>${rows}</table><div class="mut" style="margin-top:6px">Usage shifts by count and batter side; see each hitter's count view.</div>`})();
function lineup(){
 const rows=B.hitters.map((h,i)=>{const r=B.review[h.id]||{};const t=(h.targets.groups||[])[0];const tx=t?`${t.family} ${t.zone}, ${t.count}`:"not enough data";
 return `<tr class="hit ${i===H?"sel":""}" data-i="${i}"><td>${h.order}</td><td>${h.name}</td><td>${h.stand}</td><td><span class="badge">${h.profile.support}</span> <span class="mut">${h.profile.swings}</span></td>
 <td class="num">${h.profile.whiff==null?"-":pct(h.profile.whiff)} <span class="mut">vs ${pct(h.profile.league_whiff)}</span></td>
 <td class="num">${h.profile.xwobacon==null?"-":h.profile.xwobacon.toFixed(3)} <span class="mut">vs ${h.profile.league_xwobacon.toFixed(3)}</span></td>
 <td>${tx}</td><td class="num">${r.pitches?sgn(r.decision_value_runs):"-"}</td></tr>`}).join("");
 $("#lineup").innerHTML=`<tr><th>#</th><th>Hitter</th><th>Bats</th><th>Support</th><th>Whiff/swing</th><th>xwOBA on contact</th><th>Development target</th><th>Game decision value</th></tr>${rows}`;
 document.querySelectorAll("tr.hit").forEach(tr=>tr.onclick=()=>{H=+tr.dataset.i;PT=null;lineup();hitter()});
}
function grid(codes,deltas){
 let out=`<div class="axis">in &rarr; away (batter view), high at top</div><div class="grid" role="table">`;
 for(let j=NZ-1;j>=0;j--)for(let i=0;i<NX;i++){const k=i*NZ+j;const c=codes[k];const d=deltas[k];
  const bg=c==="G"?mixColor(Math.abs(d)):c==="x"?mixColor(-Math.abs(d)):"var(--mid)";
  out+=`<div class="cell" style="background:${bg}" title="${c==="G"?"swing":c==="x"?"take":"no call"}; swing minus take ${sgn(d*1)} (wOBA)">${c}</div>`}
 return out+"</div>";
}
const NAME={VALUE:"Value plan",CONTACT:"Contact-capped",HUNT:"Hunt a spot"};
const DESC={VALUE:"Swing where swinging beats taking, take where the reverse.",CONTACT:"Put it in play: drop swings likely to miss, add swings likely to make contact that are close to even.",HUNT:"Sit on one pitch type and a few spots, take the rest. Reverts to the value plan at two strikes."};
function viableOffered(){const h=B.hitters[H];const cn=h.tto[TTO][CNT];const vc=cn.differ.VALUE_vs_CONTACT>=0.05&&(cn.styles.CONTACT.value_per_100-cn.styles.VALUE.value_per_100)>=-0.5;return vc?"VALUE+CONTACT":"VALUE"}
function hitter(){
 const h=B.hitters[H];const cn=h.tto[TTO][CNT];const types=Object.keys(cn.arsenal).sort((a,b)=>cn.arsenal[b].usage-cn.arsenal[a].usage);
 if(!PT||!types.includes(PT))PT=types[0];
 const tabs=["1","2","3"].map(t=>`<button class="${t===TTO?"on":""}" data-tto="${t}">Time through order ${t}${t==="3"?"+":""}</button>`).join("");
 let cnts="";for(let s=0;s<3;s++)for(let b=0;b<4;b++){const k=b+"-"+s;cnts+=`<button class="${k===CNT?"on":""}" data-c="${k}">${k}</button>`}
 const expBtn=`<label class="mut"><input type="checkbox" id="exp" ${EXP?"checked":""}> show experimental hunt style (the model cannot value sitting on a pitch)</label>`;
 const chips=types.map(t=>`<button class="${t===PT?"on":""}" data-pt="${t}">${t} ${pct(cn.arsenal[t].usage)}</button>`).join("");
 const base=cn.styles.VALUE;
 const viableC=cn.differ.VALUE_vs_CONTACT>=0.05&&(cn.styles.CONTACT.value_per_100-base.value_per_100)>=-0.5;
 const show=["VALUE"].concat(viableC?["CONTACT"]:[]).concat(EXP?["HUNT"]:[]);
 const card=st=>{const s=cn.styles[st];
  const diff=st==="CONTACT"?cn.differ.VALUE_vs_CONTACT:st==="HUNT"?cn.differ.VALUE_vs_HUNT:null;
  const key=[B.date,B.starter.id,h.id,TTO,CNT].join("|");const cur=(LOG[key]||{}).path;
  return `<div class="card ${cur===st?"chosen":""}"><h3>${NAME[st]}${st==="HUNT"?" (experimental)":""}</h3><div>${s.tags.map(t=>`<span class="chip">${t}</span>`).join("")}</div>
  ${s.target?`<div class="mut">Hunt: ${s.target}</div>`:""}
  ${grid(s.cells[PT],cn.delta[PT])}
  <div class="mut">${DESC[st]}</div>${st==="CONTACT"&&s.value_per_100>cn.styles.VALUE.value_per_100?`<div class="mut">Reads higher than the value plan because it swings at close-to-even cells the value plan leaves without a call for thin evidence. Point estimate, less certain.</div>`:""}
  <table style="margin-top:6px"><tr><td>Swing on</td><td class="num">${pct(s.swing_share)} of his pitches</td></tr>
  <tr><td>Whiff on swings</td><td class="num">${pct(s.whiff)}</td></tr><tr><td>xwOBA on contact</td><td class="num">${s.contact.toFixed(3)}</td></tr>
  <tr><td>Value if followed</td><td class="num">${sgn(s.value_per_100)} runs / 100 pitches</td></tr>
  ${diff==null?"":`<tr><td>Differs from value plan</td><td class="num">${pct(diff)} of pitches</td></tr>`}</table>
  <div class="logrow noprint"><button data-pick="${st}">Use this plan</button></div></div>`};
 const styles=show.map(card).join("")+(show.length===1?`<div class="card"><h3>One viable plan here</h3><div class="mut">${CNT.endsWith("-2")?"With two strikes the options collapse to protecting the plate.":cn.styles.VALUE.swing_share===0?"The model sees no pitch worth swinging at in this count.":"The other style differs on under 5% of pitches or gives up more than half a run per 100 pitches, so it is not offered."}</div></div>`:"");
 const keyNow=[B.date,B.starter.id,h.id,TTO,CNT].join("|");const L=LOG[keyNow]||{};
 const logBox=`<div class="card noprint"><h3>Coach decision for ${h.name} at ${CNT}, time through order ${TTO}</h3><div class="logrow">
  <select id="lg-path"><option value="">Plan chosen</option><option value="VALUE">Value plan</option><option value="CONTACT">Contact-capped</option><option value="OWN">My own plan</option></select>
  <select id="lg-why"><option value="">Reason</option><option>hitter feel/recent form</option><option>scouting report</option><option>game situation</option><option>development goal</option><option>model looks wrong</option><option>other</option></select>
  <input type="text" id="lg-note" placeholder="note" size="28"><button id="lg-save">Save</button></div>
  <div class="note">Saved on this device. ${Object.keys(LOG).length} decisions logged. <button id="lg-export">Export log (CSV)</button></div></div>`;
 const tg=(h.targets.groups||[]).map(g=>`<li>${g.family} pitches in the ${g.zone} zone, ${g.count}: he gives up ${g.his_rate.toFixed(1)} runs per 100 such pitches vs ${g.typical_rate.toFixed(1)} for a typical hitter (${g.n} pitches, ${g.excess_per_100.toFixed(2)} runs per 100 of all his pitches)</li>`).join("")||"<li class='mut'>not enough tracked pitches</li>";
 const r=B.review[h.id];let post="";
 if(r&&r.pitches){const row=x=>`<tr><td>PA ${x.pa}</td><td>${x.count}</td><td>${x.type}</td><td>${x.region}</td><td>${x.action}</td><td>${x.result.toLowerCase().replace("_"," ")}</td><td class="num">${x.dv_runs==null?"-":sgn(x.dv_runs)}</td></tr>`;
  const head="<tr><th>PA</th><th>Count</th><th>Pitch</th><th>Where</th><th>He</th><th>Result</th><th>Value</th></tr>";
  post=`<div class="card"><h3>Post-game: ${r.pitches} pitches, decision value ${sgn(r.decision_value_runs)} runs</h3>
  <div class="mut">Good ${r.process.GOOD||0} | close call ${r.process.NEUTRAL||0} | worse than the other option ${r.process.BAD||0} | not covered ${r.process.UNSCORED||0}</div>
  <div class="two"><div><h3>Best decisions</h3><table>${head}${r.best.map(row).join("")}</table></div><div><h3>Costliest decisions</h3><table>${head}${r.worst.map(row).join("")}</table></div></div>
  <details><summary>All ${r.pitches} pitches</summary><table>${head}${r.all.map(row).join("")}</table></details></div>`}
 const sw=h.swing||{};const fmt=(t,k,d=1)=>sw[t]?sw[t][k].toFixed(d):"-";
 const swingCard=sw.bat_speed?`<div class="card"><h3>Swing profile (bat tracking, shrunk toward the league)</h3><table>
  <tr><th></th><th>His</th><th>League</th></tr>
  <tr><td>Bat speed, middle pitch (mph)</td><td class="num">${fmt("bat_speed","mid")}</td><td class="num">${fmt("bat_speed","league_mid")}</td></tr>
  <tr><td>Bat speed, two strikes (mph)</td><td class="num">${fmt("bat_speed","mid_two_strikes")}</td><td class="num">-</td></tr>
  <tr><td>Swing length (ft)</td><td class="num">${fmt("swing_length","mid",2)}</td><td class="num">${fmt("swing_length","league_mid",2)}</td></tr>
  <tr><td>Attack angle: low / middle / high pitch (deg)</td><td class="num">${fmt("attack_angle","low")} / ${fmt("attack_angle","mid")} / ${fmt("attack_angle","high")}</td><td class="num">${fmt("attack_angle","league_mid")} (mid)</td></tr>
  ${sw.tilt?`<tr><td>Swing path tilt, middle pitch (deg)</td><td class="num">${fmt("tilt","mid")}</td><td class="num">${fmt("tilt","league_mid")}</td></tr>`:""}</table>
  <div class="mut">Based on ${sw.bat_speed.n} tracked swings; ${(sw.bat_speed.kept*100).toFixed(0)}% of his own pattern is kept, the rest is the league average. Descriptive: not used in the plan yet.</div></div>`:"";
 $("#hitter").innerHTML=`<h2>${h.order}. ${h.name} (${h.stand}) <span class="badge">${h.profile.support} support</span></h2>
 <div class="card"><div class="tabs">${tabs}</div><div class="counts">${cnts}</div><div class="tabs">${chips}</div><div>${expBtn}</div>
 <div class="mut">Showing ${h.name} against ${B.starter.name}'s ${PT} at ${CNT}, time through the order ${TTO}. G swing, x take, . no call (thin evidence or too close).</div>
 <div class="styles">${styles}</div>${logBox}</div>
 <div class="two" style="margin-top:12px">${swingCard}<div class="card"><h3>Development targets (his past decisions vs an average-hitter model)</h3><ul>${tg}</ul><div class="mut">Where his swing/take choices cost more than a typical hitter's so far. Descriptive, not a diagnosis.</div></div>${post}</div>`;
 const eb=document.getElementById("exp");if(eb)eb.onchange=()=>{EXP=eb.checked;hitter()};
 document.querySelectorAll("[data-tto]").forEach(b=>b.onclick=()=>{TTO=b.dataset.tto;hitter()});
 document.querySelectorAll("[data-c]").forEach(b=>b.onclick=()=>{CNT=b.dataset.c;hitter()});
 document.querySelectorAll("[data-pt]").forEach(b=>b.onclick=()=>{PT=b.dataset.pt;hitter()});
 document.querySelectorAll("[data-pick]").forEach(b=>b.onclick=()=>{const k=[B.date,B.starter.id,h.id,TTO,CNT].join("|");LOG[k]=Object.assign(LOG[k]||{},{path:b.dataset.pick,saved:new Date().toISOString(),hitter:h.name,hitter_id:h.id,starter:B.starter.name,date:B.date,tto:TTO,count:CNT});saveLog();hitter()});
 const sv=document.getElementById("lg-save");if(sv){const k=[B.date,B.starter.id,h.id,TTO,CNT].join("|");const cur=LOG[k]||{};
  document.getElementById("lg-path").value=cur.path||"";document.getElementById("lg-why").value=cur.why||"";document.getElementById("lg-note").value=cur.note||"";
  sv.onclick=()=>{LOG[k]=Object.assign(cur,{path:document.getElementById("lg-path").value,why:document.getElementById("lg-why").value,note:document.getElementById("lg-note").value,saved:new Date().toISOString(),hitter:h.name,hitter_id:h.id,starter:B.starter.name,date:B.date,tto:TTO,count:CNT,offered:viableOffered()});saveLog();hitter()};
  document.getElementById("lg-export").onclick=()=>{const rows=[["date","starter","hitter","hitter_id","tto","count","offered","path","reason","note","saved"]].concat(Object.values(LOG).map(r=>[r.date,r.starter,r.hitter,r.hitter_id,r.tto,r.count,r.offered||"",r.path||"",r.why||"",(r.note||"").replace(/"/g,"'"),r.saved]));
   const csv=rows.map(r=>r.map(x=>'"'+String(x==null?"":x)+'"').join(",")).join("\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="gameplan_decisions.csv";a.click()}}
}
lineup();hitter();
</script></body></html>"""


def render(board: dict) -> str:
    return PAGE.replace("__DATA__", json.dumps(board, separators=(",", ":")))
