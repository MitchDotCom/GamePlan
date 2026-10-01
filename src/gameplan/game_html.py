"""Single-file HTML for the full-game viewer (see game.py). No external dependencies; data is embedded JSON.

Views: Game (innings grid, plate appearances, pitch by pitch against the plan in force), Pregame board (every count, time
through the order, approach styles), Hitters (swing profile, development targets, this game), Decision log (saved on this
device, exportable). Colors: blue / red diverging pair around gray for swing-better / take-better, always with a letter."""
from __future__ import annotations

import json

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GamePlan Game Viewer</title>
<style>
:root{color-scheme:light;--bg:#fcfcfb;--panel:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--line:#e3e2dd;--pos:#2a78d6;--neg:#e34948;--mid:#f0efec;--accent:#2a78d6;--warn:#fab219;--good:#0ca30c}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#1a1a19;--panel:#222221;--ink:#ffffff;--ink2:#c3c2b7;--line:#383835;--pos:#3987e5;--neg:#e66767;--mid:#383835;--accent:#3987e5}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#1a1a19;--panel:#222221;--ink:#ffffff;--ink2:#c3c2b7;--line:#383835;--pos:#3987e5;--neg:#e66767;--mid:#383835;--accent:#3987e5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1320px;margin:0 auto;padding:12px 16px}
h1{font-size:21px;margin:0}h2{font-size:17px;margin:16px 0 8px}h3{font-size:14px;margin:0 0 6px;color:var(--ink2);font-weight:600}
.top{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.banner{background:var(--mid);border-left:4px solid var(--warn);padding:7px 12px;border-radius:4px;margin:8px 0;color:var(--ink2);font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:middle}th{color:var(--ink2);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;border:1px solid var(--line);color:var(--ink2)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
button,select,input[type=text]{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:4px 10px}
button{cursor:pointer}button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.mut{color:var(--ink2);font-size:13px}.num{font-variant-numeric:tabular-nums}.note{font-size:12px;color:var(--ink2)}
.inn{display:grid;grid-template-columns:70px repeat(var(--n),minmax(92px,1fr));gap:4px;overflow-x:auto}
.inn .h{font-size:12px;color:var(--ink2);text-align:center;padding:2px}.inn .t{font-weight:600;font-size:13px;display:flex;align-items:center}
.cellc{display:flex;flex-direction:column;gap:3px;min-height:34px}
.pa{border:1px solid var(--line);border-radius:6px;padding:2px 6px;font-size:12px;cursor:pointer;background:var(--panel);display:flex;justify-content:space-between;gap:6px}
.pa:hover{outline:1px solid var(--accent)}.pa.sel{outline:2px solid var(--accent)}.pa .r{font-weight:600}
.k-hit{border-left:4px solid var(--pos)}.k-bb{border-left:4px solid #7aa7e8}.k-k{border-left:4px solid var(--neg)}.k-out{border-left:4px solid var(--ink2)}
.rel{opacity:.65}
.grid{display:grid;grid-template-columns:repeat(5,34px);gap:2px;margin:8px 0}
.cell{width:34px;height:30px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;border-radius:3px;background:var(--mid);color:var(--ink2)}
.mini{display:inline-grid;grid-template-columns:repeat(5,15px);gap:1px;position:relative;width:max-content}
.mini .c{width:15px;height:13px;font-size:9px;display:flex;align-items:center;justify-content:center;border-radius:2px;background:var(--mid);color:var(--ink2)}
.dotw{position:absolute;inset:0;pointer-events:none}.dot{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--ink);border:2px solid var(--panel);transform:translate(-50%,50%)}
.counts{display:grid;grid-template-columns:repeat(4,auto);gap:4px;width:max-content}
.styles{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-top:10px}
.chip{display:inline-block;margin:0 4px 4px 0;padding:1px 8px;border-radius:10px;background:var(--mid);font-size:12px}
.call{display:inline-block;min-width:22px;text-align:center;border-radius:4px;padding:0 6px;font-weight:700;background:var(--mid)}
.lab-ok{color:var(--good)}.lab-bad{color:var(--neg)}.lab-lucky{color:var(--accent)}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.chosen{outline:2px solid var(--accent)}.logrow{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px}
details summary{cursor:pointer;color:var(--ink2)}
@media print{.noprint{display:none}body{font-size:12px}.card{break-inside:avoid}}
</style></head><body><div class="wrap">
<div class="top"><h1 id="title"></h1><div class="tabs noprint" id="views"></div>
<label class="mut noprint">Runner on third, fewer than 2 outs: <select id="pol"><option value="OFF">count-only plan</option><option value="CONTACT_FIRST">contact first</option></select></label>
<label class="mut noprint">Show: <select id="team"></select></label></div>
<div class="banner">Public 2025 MLB data, every plan fit only on games before the game date. Plans exist for plate appearances against the opposing starter; relievers are shown without a plan (the engine is starters-only). For feedback on usefulness, not a validated product, and not tested at Single-A.</div>
<div id="main"></div>
</div>
<script>
const G=__DATA__;
const $=(s,r=document)=>r.querySelector(s);
const pct=x=>(100*x).toFixed(0)+"%";const sgn=x=>(x>=0?"+":"")+x.toFixed(2);
const SYM={G:"G",x:"x",".":"."};
let VIEW="game",TEAM="all",POL="OFF",SELPA=G.pas[0].id,SELPITCH=0;
let HALF="Top",HI=0,TTO="1",CNT="0-0",PT=null,EXP=false;
let LOG={};try{LOG=JSON.parse(localStorage.getItem("gameplanLog2")||"{}")}catch(e){LOG={}}
const saveLog=()=>{try{localStorage.setItem("gameplanLog2",JSON.stringify(LOG))}catch(e){}};
const mix=d=>{const a=Math.min(Math.abs(d)/0.12,1);const c=d>=0?"var(--pos)":"var(--neg)";return `color-mix(in srgb, ${c} ${Math.round(20+60*a)}%, var(--mid))`};
const SHORT={Strikeout:"K",Walk:"BB","Intentional walk":"IBB","Hit by pitch":"HBP",Single:"1B",Double:"2B",Triple:"3B","Home run":"HR","Out in play":"Out","Force out":"FO","Double play":"DP","Sacrifice fly":"SF","Sacrifice bunt":"SH","Reached on error":"E","Fielder's choice":"FC"};
const short=r=>SHORT[r]||r.split(" ")[0];
const last=n=>{const p=(n||"").split(" ");return p[p.length-1]};
const side=h=>G.sides[h];
$("#title").textContent=`${G.away} @ ${G.home}, ${G.date}`;
$("#views").innerHTML=[["game","Game"],["board","Pregame board"],["hitters","Hitters"],["log","Decision log"]].map(([k,t])=>`<button data-v="${k}">${t}</button>`).join("");
$("#team").innerHTML=`<option value="all">Both teams</option><option value="Top">${G.away} batting</option><option value="Bot">${G.home} batting</option>`;
$("#team").onchange=e=>{TEAM=e.target.value;render()};$("#pol").onchange=e=>{POL=e.target.value;render()};
document.querySelectorAll("[data-v]").forEach(b=>b.onclick=()=>{VIEW=b.dataset.v;render()});
const planOf=p=>p.plan?p.plan.policy[p.plan.spot?POL:"OFF"]:null;
function callChip(c){const t=c==="GO"?"G":c==="NO_GO"?"x":c==="CONDITIONAL"?".":"-";const bg=c==="GO"?"color-mix(in srgb, var(--pos) 55%, var(--mid))":c==="NO_GO"?"color-mix(in srgb, var(--neg) 55%, var(--mid))":"var(--mid)";return `<span class="call" style="background:${bg}" title="${c==="GO"?"swing":c==="NO_GO"?"take":"no call"}">${t}</span>`}
function miniGrid(p){if(!p.plan||!p.plan.grid)return "";const g=p.plan.grid,d=p.plan.deltas;let h="";
 for(let j=5;j>=0;j--)for(let i=0;i<5;i++){const k=i*6+j,c=g[k];h+=`<div class="c" style="background:${c==="G"?mix(Math.abs(d[k])):c==="x"?mix(-Math.abs(d[k])):"var(--mid)"}">${c==="."?"":c}</div>`}
 const left=((p.x+1.25)/2.5)*100,bot=((p.z-1)/3)*100;
 return `<div class="mini">${h}<div class="dotw"><div class="dot" style="left:${Math.max(0,Math.min(100,left))}%;bottom:${Math.max(0,Math.min(100,bot))}%"></div></div></div>`}
const LBL={FOLLOWED_PLAN:["Followed the plan","lab-ok"],HITTER_BEAT_MODEL:["Left the plan and it worked","lab-lucky"],DEVIATION_COST:["Left the plan, cost him","lab-bad"],UMPIRE_MISS:["Umpire miss","lab-lucky"],PLAN_SILENT:["No strong call",""]};
function innings(){const filt=p=>TEAM==="all"||p.half===TEAM;const n=Math.max(9,...G.pas.map(p=>p.inning));
 let h=`<div class="inn" style="--n:${n}"><div></div>`+Array.from({length:n},(_,i)=>`<div class="h">${i+1}</div>`).join("");
 for(const half of ["Top","Bot"]){if(TEAM!=="all"&&TEAM!==half)continue;h+=`<div class="t">${half==="Top"?G.away:G.home}</div>`;
  for(let i=1;i<=n;i++){const ps=G.pas.filter(p=>p.half===half&&p.inning===i&&filt(p));
   h+=`<div class="cellc">${ps.map(p=>`<div class="pa k-${p.kind} ${p.vs_starter?"":"rel"} ${p.id===SELPA?"sel":""}" data-pa="${p.id}" title="${p.batter_name} vs ${p.pitcher_name}: ${p.result}"><span>${last(p.batter_name)}</span><span class="r">${short(p.result)}</span></div>`).join("")}</div>`}}
 return h+"</div>"}
function paPanel(){const p=G.pas.find(x=>x.id===SELPA);if(!p)return "";
 const rows=p.pitches.map((q,i)=>{const pl=planOf(q);let lab=pl?(LBL[pl.label]||[pl.label,""]):["",""];if(pl&&pl.call==="CONDITIONAL"&&pl.label==="FOLLOWED_PLAN")lab=["Took the better option (thin evidence, no firm call)",""];
  return `<tr data-pi="${i}" style="${i===SELPITCH?"background:var(--mid)":""}"><td>${q.n}</td><td>${q.count}</td><td>${q.type||""} ${q.velo?q.velo.toFixed(1):""}</td><td>${q.region||"-"}</td><td>${q.swing===undefined?"-":q.swing?"swung":"took"}</td><td>${q.desc}</td>
  <td>${pl?callChip(pl.call):"-"} <span class="mut num">${pl&&pl.delta!=null?sgn(pl.delta):""}</span></td><td class="num">${pl&&pl.dv!=null?sgn(pl.dv):"-"}</td><td class="${lab[1]}">${lab[0]}${pl&&pl.flags.includes("umpire_miss")?" (umpire miss)":""}</td><td>${miniGrid(q)}</td></tr>`}).join("");
 const sd=side(p.half);const tag=p.vs_starter?`<span class="badge">starter: plan applies</span>`:`<span class="badge">reliever: no plan</span>`;
 return `<div class="card"><h3>${G.pas.indexOf(p)+1}. ${p.team} ${p.half==="Top"?"top":"bottom"} ${p.inning}: ${p.batter_name} (${p.stand}) vs ${p.pitcher_name} ${tag}</h3>
 <div class="mut">${p.outs} out, bases ${p.bases}, ${p.lead===0?"tied":(p.lead>0?"batting team up ":"batting team down ")+Math.abs(p.lead)}. Result: <b>${p.result}</b>${p.dv!=null?` | decision value ${sgn(p.dv)} runs, ${p.bad} decisions worse than the other option`:""}</div>
 <table style="margin-top:6px"><tr><th>#</th><th>Count</th><th>Pitch</th><th>Where</th><th>He</th><th>Result</th><th>Plan said</th><th>Value</th><th>Review</th><th>Plan at this pitch</th></tr>${rows}</table>
 <div class="note">Plan said: G swing, x take, . no strong call. Value = decision value in runs (positive: better than the other option). The small grid is the plan for that pitch type, batter's view, dot = where the pitch went. ${p.pitches.some(q=>q.plan&&q.plan.spot)?"Runner on third with fewer than 2 outs: the top selector switches between the count-only plan and the contact-first policy.":""}</div>
 <div class="logrow noprint"><button data-hit="${p.batter}">Open ${last(p.batter_name)}'s pregame board</button></div></div>`}
function gameView(){const lg=`<div class="note" style="margin:6px 0">Bar colour: blue hit or walk, red strikeout, gray out. Faded = reliever (no plan). Click a plate appearance.</div>`;
 const tot=G.pas.filter(p=>p.dv!=null&&(TEAM==="all"||p.half===TEAM));const dv=tot.reduce((a,p)=>a+p.dv,0),bad=tot.reduce((a,p)=>a+p.bad,0);
 const pl=tot.flatMap(p=>p.pitches).filter(x=>x.plan).map(x=>x.plan.policy.OFF.call),silent=pl.filter(c=>c==="CONDITIONAL").length;
 return `<div class="card">${innings()}${lg}<div class="mut">Against the starters in this view: ${tot.length} plate appearances, net decision value ${sgn(dv)} runs (swing or take chosen versus the other option), ${bad} choices the model rates worse than the alternative.</div><div class="mut"><b>How often the plan speaks:</b> it gave a firm swing or take call on ${pl.length-silent} of ${pl.length} pitches (${pct(pl.length?(pl.length-silent)/pl.length:0)}). On the other ${pct(pl.length?silent/pl.length:0)} the evidence was too thin or the two options too close, so it says nothing.</div></div><div style="margin-top:12px">${paPanel()}</div>`}
/* ---------------- pregame board ---------------- */
function grid(codes,deltas){let o=`<div class="mut" style="font-size:11px">in &rarr; away (batter view), high at top</div><div class="grid">`;
 for(let j=5;j>=0;j--)for(let i=0;i<5;i++){const k=i*6+j,c=codes[k],d=deltas[k];o+=`<div class="cell" style="background:${c==="G"?mix(Math.abs(d)):c==="x"?mix(-Math.abs(d)):"var(--mid)"}" title="${c==="G"?"swing":c==="x"?"take":"no call"}; swing minus take ${sgn(d)} (wOBA)">${c}</div>`}
 return o+"</div>"}
const NAME={VALUE:"Value plan",CONTACT:"Contact-capped",HUNT:"Hunt a spot"};
const DESC={VALUE:"Swing where swinging beats taking, take where the reverse.",CONTACT:"Put it in play: drop swings likely to miss, add swings likely to make contact that are close to even.",HUNT:"Sit on one pitch type and a few spots, take the rest. The model cannot value sitting on a pitch."};
function viable(cn){return cn.differ.VALUE_vs_CONTACT>=0.05&&(cn.styles.CONTACT.value_per_100-cn.styles.VALUE.value_per_100)>=-0.5}
function boardView(){const sd=side(HALF),B=sd.board;if(HI>=B.hitters.length)HI=0;const h=B.hitters[HI];const cn=h.tto[TTO][CNT];
 const types=Object.keys(cn.arsenal).sort((a,b)=>cn.arsenal[b].usage-cn.arsenal[a].usage);if(!PT||!types.includes(PT))PT=types[0];
 const sel=`<select id="bh">${["Top","Bot"].map(hf=>side(hf).board.hitters.map((x,i)=>`<option value="${hf}|${i}" ${hf===HALF&&i===HI?"selected":""}>${hf==="Top"?G.away:G.home}: ${x.order}. ${x.name}</option>`).join("")).join("")}</select>`;
 const ars=Object.entries(B.starter.arsenal_tto1_0_0).sort((a,b)=>b[1].usage-a[1].usage).map(([k,v])=>`<tr><td>${k}</td><td class="num">${pct(v.usage)}</td><td class="num">${v.velo.toFixed(1)}</td><td class="num">${v.ivb.toFixed(1)}</td><td class="num">${v.hb.toFixed(1)}</td></tr>`).join("");
 const tabs=["1","2","3"].map(t=>`<button class="${t===TTO?"on":""}" data-tto="${t}">Time through order ${t}${t==="3"?"+":""}</button>`).join("");
 let cnts="";for(let s=0;s<3;s++)for(let b=0;b<4;b++){const k=b+"-"+s;cnts+=`<button class="${k===CNT?"on":""}" data-c="${k}">${k}</button>`}
 const chips=types.map(t=>`<button class="${t===PT?"on":""}" data-pt="${t}">${t} ${pct(cn.arsenal[t].usage)}</button>`).join("");
 const show=["VALUE"].concat(viable(cn)?["CONTACT"]:[]).concat(EXP?["HUNT"]:[]);
 const key=[G.date,sd.starter,h.id,TTO,CNT].join("|");const cur=(LOG[key]||{}).path;
 const card=st=>{const s=cn.styles[st];const diff=st==="CONTACT"?cn.differ.VALUE_vs_CONTACT:st==="HUNT"?cn.differ.VALUE_vs_HUNT:null;
  return `<div class="card ${cur===st?"chosen":""}"><h3>${NAME[st]}${st==="HUNT"?" (experimental)":""}</h3><div>${s.tags.map(t=>`<span class="chip">${t}</span>`).join("")}</div>${s.target?`<div class="mut">Hunt: ${s.target}</div>`:""}
  ${grid(s.cells[PT],cn.delta[PT])}<div class="mut">${DESC[st]}</div>${st==="CONTACT"&&s.value_per_100>cn.styles.VALUE.value_per_100?`<div class="mut">Reads higher than the value plan because it swings at close-to-even cells the value plan leaves without a call for thin evidence. Point estimate, less certain.</div>`:""}
  <table style="margin-top:6px"><tr><td>Swing on</td><td class="num">${pct(s.swing_share)} of his pitches</td></tr><tr><td>Whiff on swings</td><td class="num">${pct(s.whiff)}</td></tr><tr><td>xwOBA on contact</td><td class="num">${s.contact.toFixed(3)}</td></tr>
  <tr><td>Value if followed</td><td class="num">${sgn(s.value_per_100)} runs / 100 pitches</td></tr>${diff==null?"":`<tr><td>Differs from value plan</td><td class="num">${pct(diff)} of pitches</td></tr>`}</table>
  <div class="logrow noprint"><button data-pick="${st}">Use this plan</button></div></div>`};
 const styles=show.map(card).join("")+(show.length===1?`<div class="card"><h3>One viable plan here</h3><div class="mut">${CNT.endsWith("-2")?"With two strikes the options collapse to protecting the plate.":cn.styles.VALUE.swing_share===0?"The model sees no pitch worth swinging at in this count.":"The other style differs on under 5% of pitches or gives up more than half a run per 100 pitches, so it is not offered."}</div></div>`:"");
 const L=LOG[key]||{};
 const logBox=`<div class="card noprint" style="margin-top:12px"><h3>Coach decision for ${h.name} at ${CNT}, time through order ${TTO}</h3><div class="logrow"><select id="lg-path"><option value="">Plan chosen</option><option value="VALUE">Value plan</option><option value="CONTACT">Contact-capped</option><option value="OWN">My own plan</option></select>
  <select id="lg-why"><option value="">Reason</option><option>hitter feel/recent form</option><option>scouting report</option><option>game situation</option><option>development goal</option><option>model looks wrong</option><option>other</option></select><input type="text" id="lg-note" placeholder="note" size="28"><button id="lg-save">Save</button></div></div>`;
 const tg=(h.targets.groups||[]).map(g=>`<li>${g.family} pitches in the ${g.zone} zone, ${g.count}: he gives up ${g.his_rate.toFixed(1)} runs per 100 such pitches vs ${g.typical_rate.toFixed(1)} for a typical hitter (${g.n} pitches)</li>`).join("")||"<li class='mut'>not enough tracked pitches</li>";
 return `<div class="top"><label class="mut">Hitter: ${sel}</label></div>
 <div class="two"><div class="card"><h3>Starter: ${B.starter.name} (${B.starter.starts_before} earlier starts in the data)</h3><table><tr><th>Pitch</th><th>Usage (0-0)</th><th>Velo</th><th>IVB in</th><th>HB in</th></tr>${ars}</table></div>
 <div class="card"><h3>${h.order}. ${h.name} (${h.stand}) <span class="badge">${h.profile.support} support, ${h.profile.swings} tracked swings</span></h3><div class="mut">Whiff ${h.profile.whiff==null?"-":pct(h.profile.whiff)} (league ${pct(h.profile.league_whiff)}), xwOBA on contact ${h.profile.xwobacon==null?"-":h.profile.xwobacon.toFixed(3)} (league ${h.profile.league_xwobacon.toFixed(3)})</div><ul>${tg}</ul><div class="note">Development targets: where his choices cost more than a typical hitter's.</div></div></div>
 <div class="card" style="margin-top:12px"><div class="tabs">${tabs}</div><div class="counts">${cnts}</div><div class="tabs">${chips}</div><div><label class="mut"><input type="checkbox" id="exp" ${EXP?"checked":""}> show experimental hunt style</label></div>
 <div class="mut">${h.name} against ${B.starter.name}'s ${PT} at ${CNT}, time through the order ${TTO}. G swing, x take, . no call.</div><div class="styles">${styles}</div></div>${logBox}`}
function swingCard(h){const sw=G.swing_profiles[h];if(!sw||!sw.bat_speed)return "<div class='mut'>No bat-tracking profile.</div>";const f=(t,k,d=1)=>sw[t]?sw[t][k].toFixed(d):"-";
 return `<table><tr><th></th><th>His</th><th>League</th></tr><tr><td>Bat speed, middle pitch (mph)</td><td class="num">${f("bat_speed","mid")}</td><td class="num">${f("bat_speed","league_mid")}</td></tr>
 <tr><td>Bat speed, two strikes (mph)</td><td class="num">${f("bat_speed","mid_two_strikes")}</td><td class="num">-</td></tr><tr><td>Swing length (ft)</td><td class="num">${f("swing_length","mid",2)}</td><td class="num">${f("swing_length","league_mid",2)}</td></tr>
 <tr><td>Attack angle low / middle / high pitch (deg)</td><td class="num">${f("attack_angle","low")} / ${f("attack_angle","mid")} / ${f("attack_angle","high")}</td><td class="num">${f("attack_angle","league_mid")} (mid)</td></tr>
 ${sw.tilt?`<tr><td>Swing path tilt, middle pitch (deg)</td><td class="num">${f("tilt","mid")}</td><td class="num">${f("tilt","league_mid")}</td></tr>`:""}</table><div class="note">From ${sw.bat_speed.n} tracked swings; ${(sw.bat_speed.kept*100).toFixed(0)}% of his own pattern is kept, the rest is the league average. Descriptive: not used in the plan yet.</div>`}
let HSEL=null;
function hittersView(){const ids=[];G.pas.forEach(p=>{if(!ids.some(x=>x.id===p.batter))ids.push({id:p.batter,name:p.batter_name,half:p.half})});if(!HSEL)HSEL=ids[0].id;
 const opts=ids.map(x=>`<option value="${x.id}" ${x.id===HSEL?"selected":""}>${x.half==="Top"?G.away:G.home}: ${x.name}</option>`).join("");const mine=G.pas.filter(p=>p.batter===HSEL);
 const rows=mine.map(p=>`<tr class="hp" data-pa="${p.id}" style="cursor:pointer"><td>${p.inning}${p.half==="Top"?"T":"B"}</td><td>${p.pitcher_name}${p.vs_starter?"":" (reliever)"}</td><td>${p.result}</td><td class="num">${p.dv==null?"-":sgn(p.dv)}</td><td class="num">${p.bad==null?"-":p.bad}</td></tr>`).join("");
 return `<div class="top"><label class="mut">Hitter: <select id="hs">${opts}</select></label></div><div class="two"><div class="card"><h3>Swing profile</h3>${swingCard(HSEL)}</div><div class="card"><h3>This game</h3><table><tr><th>Inning</th><th>Pitcher</th><th>Result</th><th>Decision value</th><th>Worse than other option</th></tr>${rows}</table><div class="note">Click a row to see the pitches.</div></div></div>`}
function logView(){const rows=Object.values(LOG).sort((a,b)=>(b.saved||"").localeCompare(a.saved||"")).map(r=>`<tr><td>${r.hitter}</td><td>${r.tto}</td><td>${r.count}</td><td>${r.path||""}</td><td>${r.why||""}</td><td>${r.note||""}</td></tr>`).join("");
 return `<div class="card"><h3>Coach decisions saved on this device</h3><table><tr><th>Hitter</th><th>TTO</th><th>Count</th><th>Plan</th><th>Reason</th><th>Note</th></tr>${rows||"<tr><td colspan=6 class='mut'>Nothing saved yet. Choose a plan on the pregame board.</td></tr>"}</table><div class="logrow"><button id="lg-export">Export CSV</button></div></div>`}
function wire(){
 document.querySelectorAll("[data-pa]").forEach(e=>e.onclick=()=>{SELPA=+e.dataset.pa;SELPITCH=0;VIEW="game";render()});
 document.querySelectorAll("[data-pi]").forEach(e=>e.onclick=()=>{SELPITCH=+e.dataset.pi;render()});
 document.querySelectorAll("[data-hit]").forEach(e=>e.onclick=()=>{const id=e.dataset.hit;for(const hf of ["Top","Bot"]){const i=side(hf).board.hitters.findIndex(x=>x.id===id);if(i>=0){HALF=hf;HI=i;VIEW="board";render();return}}});
 document.querySelectorAll("[data-tto]").forEach(b=>b.onclick=()=>{TTO=b.dataset.tto;render()});document.querySelectorAll("[data-c]").forEach(b=>b.onclick=()=>{CNT=b.dataset.c;render()});document.querySelectorAll("[data-pt]").forEach(b=>b.onclick=()=>{PT=b.dataset.pt;render()});
 const bh=$("#bh");if(bh)bh.onchange=e=>{const [hf,i]=e.target.value.split("|");HALF=hf;HI=+i;PT=null;render()};
 const hs=$("#hs");if(hs)hs.onchange=e=>{HSEL=e.target.value;render()};
 const ex=$("#exp");if(ex)ex.onchange=()=>{EXP=ex.checked;render()};
 const sd=side(HALF),h=sd.board.hitters[HI];
 const meta=()=>({hitter:h.name,hitter_id:h.id,starter:sd.board.starter.name,date:G.date,tto:TTO,count:CNT,saved:new Date().toISOString(),offered:viable(h.tto[TTO][CNT])?"VALUE+CONTACT":"VALUE"});
 const key=[G.date,sd.starter,h.id,TTO,CNT].join("|");
 document.querySelectorAll("[data-pick]").forEach(b=>b.onclick=()=>{LOG[key]=Object.assign(LOG[key]||{},meta(),{path:b.dataset.pick});saveLog();render()});
 const sv=$("#lg-save");if(sv){const cur=LOG[key]||{};$("#lg-path").value=cur.path||"";$("#lg-why").value=cur.why||"";$("#lg-note").value=cur.note||"";sv.onclick=()=>{LOG[key]=Object.assign(cur,meta(),{path:$("#lg-path").value,why:$("#lg-why").value,note:$("#lg-note").value});saveLog();render()}}
 const ex2=$("#lg-export");if(ex2)ex2.onclick=()=>{const rows=[["date","starter","hitter","hitter_id","tto","count","offered","path","reason","note","saved"]].concat(Object.values(LOG).map(r=>[r.date,r.starter,r.hitter,r.hitter_id,r.tto,r.count,r.offered||"",r.path||"",r.why||"",(r.note||"").replace(/"/g,"'"),r.saved]));
  const csv=rows.map(r=>r.map(x=>'"'+String(x==null?"":x)+'"').join(",")).join("\n");let box=$("#lg-csv");if(!box){box=document.createElement("div");box.id="lg-csv";ex2.parentNode.parentNode.appendChild(box)}
  box.innerHTML='<div class="mut" style="margin-top:8px">Copy this into a spreadsheet.</div><textarea id="lg-csv-text" rows="8" style="width:100%"></textarea><div class="logrow"><button id="lg-copy">Copy</button></div>';
  const ta=$("#lg-csv-text");ta.value=csv;ta.select();$("#lg-copy").onclick=()=>{ta.select();try{navigator.clipboard.writeText(csv).catch(()=>{})}catch(e){}}}}
function render(){document.querySelectorAll("[data-v]").forEach(b=>b.classList.toggle("on",b.dataset.v===VIEW));
 $("#main").innerHTML=VIEW==="game"?gameView():VIEW==="board"?boardView():VIEW==="hitters"?hittersView():logView();wire()}
render();
</script></body></html>"""


def render(game: dict) -> str:
    return PAGE.replace("__DATA__", json.dumps(game, separators=(",", ":")))
