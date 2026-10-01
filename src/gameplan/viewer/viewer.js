const EMBED=__DATA__;let G=EMBED;const SERVER=EMBED===null;
const $=(s,r=document)=>r.querySelector(s);
const pct=x=>(100*x).toFixed(0)+"%";const sgn=x=>(x>=0?"+":"")+x.toFixed(2);
const SYM={G:"G",x:"x",".":"."};
let VIEW="game",TEAM="all",POL="OFF",SELPA=0,SELPITCH=0;
let HALF="Top",HI=0,TTO="1",CNT="0-0",PT=null,EXP=false;
let LOG={},saveT=null;
async function loadLog(){if(SERVER){try{LOG=await (await fetch("/api/log")).json()}catch(e){LOG={}}}else{try{LOG=JSON.parse(localStorage.getItem("gameplanLog2")||"{}")}catch(e){LOG={}}}}
const saveLog=()=>{if(SERVER){clearTimeout(saveT);saveT=setTimeout(()=>fetch("/api/log",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(LOG)}).catch(()=>{}),150)}else{try{localStorage.setItem("gameplanLog2",JSON.stringify(LOG))}catch(e){}}};
const mix=d=>{const a=Math.min(Math.abs(d)/0.12,1);const c=d>=0?"var(--pos)":"var(--neg)";return `color-mix(in srgb, ${c} ${Math.round(20+60*a)}%, var(--mid))`};
const SHORT={Strikeout:"K",Walk:"BB","Intentional walk":"IBB","Hit by pitch":"HBP",Single:"1B",Double:"2B",Triple:"3B","Home run":"HR","Out in play":"Out","Force out":"FO","Double play":"DP","Sacrifice fly":"SF","Sacrifice bunt":"SH","Reached on error":"E","Fielder's choice":"FC"};
const short=r=>SHORT[r]||r.split(" ")[0];
const last=n=>{const p=(n||"").split(" ");return p[p.length-1]};
const side=h=>G.sides[h];
function initGame(g){G=g;Object.keys(BOARDS).forEach(k=>delete BOARDS[k]);SELPA=g.pas[0].id;SELPITCH=0;TEAM="all";HALF="Top";HI=0;TTO="1";CNT="0-0";PT=null;HSEL=null;
 $("#title").textContent=`${G.away} at ${G.home} \u00b7 ${G.date}`;
 $("#team").innerHTML=`<option value="all">Both</option><option value="Top">${G.away}</option><option value="Bot">${G.home}</option>`;$("#team").value="all"}
function buildTabs(){const tabs=(SERVER?[["library","Games"]]:[]).concat(G?[["game","Game"],["board","Pregame"],["hitters","Hitters"],["log","Log"]]:[]);
 $("#views").innerHTML=tabs.map(([k,t])=>`<button data-v="${k}">${t}</button>`).join("");
 document.querySelectorAll("[data-v]").forEach(b=>b.onclick=()=>{if(b.dataset.v==="library"){location.hash="#/"}else{VIEW=b.dataset.v;render()}})}
$("#team").onchange=e=>{TEAM=e.target.value;render()};$("#pol").onchange=e=>{POL=e.target.value;render()};$("#vside").onchange=e=>{VIEWSIDE=e.target.value;render()};
const planOf=p=>p.plan?p.plan.policy[p.plan.spot?POL:"OFF"]:null;
let SKIPMODE="exclude";
const skipKey=p=>"skip|"+G.date+"|"+G.game_pk+"|"+p.id;
const SKIP_WHY=["Bunt or sacrifice","Intentional walk","Hit and run or called play","Hitter told to take","Injury or substitution","Other"];
function autoSkip(p){const d=p.pitches.map(q=>q.desc),v=p.pitches.filter(q=>q.velo).map(q=>q.velo);
 if(d.some(x=>/bunt/.test(x))||p.result==="Sacrifice bunt")return "Bunt attempt";
 if(p.result==="Intentional walk")return "Intentional walk";
 if(p.result==="Catcher interference")return "Catcher interference";
 if(d.some(x=>/automatic/.test(x)))return "Automatic ball or strike";
 if(v.length&&v.reduce((a,b)=>a+b,0)/v.length<70)return "Position player pitching";
 return ""}
function skipInfo(p){const m=LOG[skipKey(p)],auto=autoSkip(p);
 if(m)return m.path==="SKIP"?{skipped:true,reason:m.why||"Coach decision",by:"coach"}:{skipped:false,reason:auto,by:"coach",overridden:!!auto};
 return auto?{skipped:true,reason:auto,by:"auto"}:{skipped:false,reason:"",by:""}}
const counted=p=>!(skipInfo(p).skipped&&SKIPMODE==="exclude");
function paStats(p){let dv=0,bad=0,n=0,silent=0;for(const q of p.pitches){const l=planOf(q);if(!l||/pitchout/.test(q.desc))continue;n++;if(l.call==="CONDITIONAL")silent++;if(l.dv!=null)dv+=l.dv;if(l.process==="BAD")bad++}return{dv,bad,n,silent}}
const PN={FF:"Four-seam fastball",SI:"Sinker",FC:"Cutter",SL:"Slider",ST:"Sweeper",SV:"Slurve",CU:"Curveball",KC:"Knuckle curve",CS:"Slow curve",CH:"Changeup",FS:"Splitter",FO:"Forkball",SC:"Screwball",KN:"Knuckleball",EP:"Eephus"};
const pname=c=>PN[c]||c||"Unknown pitch";
const cap=s=>s?s.charAt(0).toUpperCase()+s.slice(1):s;
const KIND=d=>/swinging|missed/.test(d)?"whiff":/foul/.test(d)?"foul":/in play/.test(d)?"play":/called|automatic strike/.test(d)?"called":"ball";
function where(q){if(q.x==null)return "Not tracked";
 const zt=q.sz_top||3.5,zb=q.sz_bot||1.5,fr=(q.z-zb)/(zt-zb),ax=Math.abs(q.x);
 const v=fr>1?"Above zone":fr<0?"Below zone":fr>2/3?"High":fr<1/3?"Low":"Middle";
 const h=ax<=0.28?"middle":ax<=0.83?(q.x<0?"inside":"away"):(q.x<0?"off plate, inside":"off plate, away");
 return v+", "+h}
function basesText(b){if(b==="empty")return "Bases empty";const m={"1B":"1st","2B":"2nd","3B":"3rd"},ps=b.split("-").map(x=>m[x]);return ps.length===3?"Bases loaded":"On "+ps.join(", ")}
const leadText=l=>l===0?"Tied":l>0?"Up "+l:"Down "+(-l);
const doWord=q=>/bunt/.test(q.desc)?"Bunted":q.swing===undefined?"Not tracked":q.swing?"Swung":"Took";
const callWord=c=>c==="GO"?"Swing":c==="NO_GO"?"Take":"No call";
const REV={FOLLOWED_PLAN:["Followed plan","lab-ok"],HITTER_BEAT_MODEL:["Off plan, worked","lab-lucky"],DEVIATION_COST:["Off plan, cost","lab-bad"],UMPIRE_MISS:["Umpire miss","lab-lucky"],PLAN_SILENT:["No call",""],NO_CALL_OK:["Better option, no call",""]};
function review(q){const pl=planOf(q);if(!pl)return null;const k=pl.call==="CONDITIONAL"&&pl.label==="FOLLOWED_PLAN"?"NO_CALL_OK":pl.label;return REV[k]||[cap(String(k).toLowerCase().replace(/_/g," ")),""]}
function zoneSVG(codes,deltas,o={}){
 /* Feet to SVG units: 100 per foot. x runs 3.0 ft (+-1.5), z runs 0.75 to 4.25 ft. xa is feet away from the batter. */
 const U=100,X0=-1.5,Z1=4.25,W=300,H=350,pad=14,mir=VIEWSIDE==="catcher"&&o.stand==="L";
 const ux=xa=>((mir?-xa:xa)-X0)*U,uy=z=>(Z1-z)*U,bx=(a,b)=>Math.min(ux(a),ux(b));
 const tipPlan=c=>c==="G"?"Swing":c==="x"?"Take":"No call";
 let s=`<svg class="zone ${o.small?"small":""}" viewBox="${-pad} ${-pad} ${W+2*pad} ${H+pad+56}" role="img" aria-label="Strike zone, ${VIEWSIDE==="catcher"?"catcher view":"batter view"}">`;
 s+=`<rect x="0" y="0" width="${W}" height="${H}" fill="var(--panel)" stroke="var(--line)"/>`;
 for(let i=0;i<5;i++)for(let j=0;j<6;j++){const k=i*6+j,c=codes?codes[k]:".",d=deltas?deltas[k]:0,a=-1.25+i*0.5,zt=1.0+(j+1)*0.5;
  const fill=c==="G"?mix(Math.abs(d)):c==="x"?mix(-Math.abs(d)):"var(--mid)",x=bx(a,a+0.5),y=uy(zt);
  s+=`<g><title>${tipPlan(c)}${codes?"; swing minus take "+sgn(d)+" wOBA":""}</title><rect x="${x}" y="${y}" width="50" height="50" fill="${fill}" stroke="var(--panel)" stroke-width="1.5"/>${c==="G"||c==="x"?`<text x="${x+25}" y="${y+29}" text-anchor="middle" class="zl">${tipPlan(c)}</text>`:""}</g>`}
 const zt=o.szTop||3.5,zb=o.szBot||1.5;
 s+=`<rect x="${bx(-0.83,0.83)}" y="${uy(zt)}" width="166" height="${(zt-zb)*U}" fill="none" stroke="var(--ink)" stroke-width="2.5" pointer-events="none"/>`;
 const cx0=ux(0),inL=!mir,lab=(txt,left)=>`<text x="${left?0:W}" y="${H+30}" text-anchor="${left?"start":"end"}" class="zlab">${txt}</text>`;
 s+=`<polygon points="${cx0-71},${H+10} ${cx0+71},${H+10} ${cx0+71},${H+22} ${cx0},${H+36} ${cx0-71},${H+22}" fill="var(--mid)" stroke="var(--ink2)" stroke-width="1.5"/>`+lab("Inside"+(o.stand?" ("+o.stand+"HB)":""),inL)+lab("Away",!inL);
 (o.pitches||[]).forEach((q,idx)=>{if(q.x==null)return;if(o.showAll===false&&idx>o.sel)return;
  const rx=ux(q.x),ry=uy(q.z),off=rx<12||rx>W-12||ry<12||ry>H-12,cx=Math.max(12,Math.min(W-12,rx)),cy=Math.max(12,Math.min(H-12,ry)),k=KIND(q.desc),cur=idx===o.sel;
  s+=`<g class="pt" data-n="${q.n}" data-cx="${rx.toFixed(1)}" data-cy="${ry.toFixed(1)}" opacity="${cur||o.sel<0?1:.72}"><title>Pitch ${q.n}: ${pname(q.type)}, ${cap(q.desc)}</title>${cur?`<circle cx="${cx}" cy="${cy}" r="16" fill="none" stroke="var(--brand)" stroke-width="3"/>`:""}<circle cx="${cx}" cy="${cy}" r="11" class="k-${k}" ${off?'stroke-dasharray="3 2"':""}/><text x="${cx}" y="${cy+4}" class="pn pn-${k}">${q.n}</text></g>`});
 return s+"</svg>"}
let SHOWALL=true,VIEWSIDE="catcher";
function step(d){const p=G.pas.find(x=>x.id===SELPA);if(!p)return;SELPITCH=Math.max(0,Math.min(p.pitches.length-1,SELPITCH+d));render()}
function innings(){const filt=p=>TEAM==="all"||p.half===TEAM;const n=Math.max(9,...G.pas.map(p=>p.inning));
 let h=`<div class="inn" style="--n:${n}"><div></div>`+Array.from({length:n},(_,i)=>`<div class="h">${i+1}</div>`).join("");
 for(const half of ["Top","Bot"]){if(TEAM!=="all"&&TEAM!==half)continue;h+=`<div class="t">${half==="Top"?G.away:G.home}</div>`;
  for(let i=1;i<=n;i++){const ps=G.pas.filter(p=>p.half===half&&p.inning===i&&filt(p));
   h+=`<div class="cellc">${ps.map(p=>`<div class="pa k-${p.kind} ${p.vs_starter?"":"rel"} ${skipInfo(p).skipped?"skip":""} ${p.id===SELPA?"sel":""}" data-pa="${p.id}" title="${p.batter_name} vs ${p.pitcher_name}: ${p.result}${skipInfo(p).skipped?" (skipped: "+skipInfo(p).reason+")":""}"><span><i></i> ${last(p.batter_name)}</span><span class="r">${short(p.result)}</span></div>`).join("")}</div>`}}
 return h+"</div>"}
const FAMN={FB:"Fastball",BRK:"Breaking",OFF:"Offspeed",OTHER:"Other"},ZONEN={heart:"Heart",shadow:"Edges",chase:"Chase"};
const CATN={damage:"Damage pitch",average:"Average pitch",weak:"Weak spot"},CATC={damage:"lab-ok",average:"",weak:"lab-bad"};
const BANDN={matched:["In band","lab-ok"],edge:["Near band",""],steep:["Too steep","lab-bad"],flat:["Too flat","lab-bad"],unknown:["n/a",""]};
function bandName(band,sw){if(!sw)return BANDN[band]||BANDN.unknown;
 return {matched:["Inside his band","lab-ok"],edge:["Near his band",""],steep:["Above his band","lab-bad"],flat:["Below his band","lab-bad"]}[band]||BANDN.unknown}
const bandTip=sw=>sw?`His whiff rate is lowest when the bat path and pitch are ${sw[0]} to ${sw[1]} degrees apart.`:"League band: 6 to 24 degrees apart.";
function curveSVG(a){if(!a.curve)return `<div class="note">League band applies: fewer than 100 swings with attack angle (${a.n_aa}).</div>`;
 const c=a.curve,W=340,H=165,L=36,R=10,T=10,B=28,ym=Math.max(.5,...c.his,...c.lg)*1.08,X=v=>L+(v-0)/36*(W-L-R),Y=p=>T+(1-p/ym)*(H-T-B);
 const pl=arr=>c.vba.map((v,i)=>X(v).toFixed(1)+","+Y(arr[i]).toFixed(1)).join(" ");
 const sw=a.sweet?`<rect x="${X(a.sweet[0])}" y="${T}" width="${Math.max(X(a.sweet[1])-X(a.sweet[0]),3)}" height="${H-T-B}" fill="var(--accent)" opacity=".14"/>`:"";
 const xt=[0,12,24,36].map(v=>`<text x="${X(v)}" y="${H-12}" text-anchor="middle" class="zlab">${v}</text>`).join(""),yt=[0,.25,.5].filter(v=>v<ym).map(v=>`<text x="${L-4}" y="${Y(v)+3}" text-anchor="end" class="zlab">${pct(v)}</text><line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/>`).join("");
 return `<div style="margin:6px 0"><svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W+60}px;height:auto" role="img" aria-label="Whiff rate by bat path versus pitch angle, him and league">${yt}${sw}<polyline points="${pl(c.lg)}" fill="none" stroke="var(--ink2)" stroke-width="2" stroke-dasharray="4 3"/><polyline points="${pl(c.his)}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>${xt}<text x="${(L+W-R)/2}" y="${H-1}" text-anchor="middle" class="zlab">Bat path minus pitch angle (degrees)</text></svg>
 <div class="note">Whiff rate by bat-to-pitch angle. Solid: his curve. Dashed: league. Shaded: his band, ${a.sweet[0]} to ${a.sweet[1]} degrees (${a.n_aa} swings, shrunk toward league).</div></div>`}
const f1=(v,d=1)=>v==null?"-":(+v).toFixed(d);

function swingBox(q){if(q.swing===false||/bunt/.test(q.desc))return "";const b=q.bt;if(!b)return q.swing?`<p class="note">No bat tracking on this swing.</p>`:"";
 const e=b.exp||{},bd=bandName(b.band,b.sweet),row=(l,v,x,d)=>`<tr><td>${l}</td><td class="num">${f1(v,d)}</td><td class="num">${x?f1(x[0],d):"-"}</td><td class="num">${x?f1(x[1],d):"-"}</td></tr>`;
 return `<h3 style="margin-top:var(--s4)">Swing</h3><div class="tw"><table><tr><th></th><th class="num">This swing</th><th class="num">His usual</th><th class="num">League</th></tr>${row("Bat speed (mph)",b.bs,e.bs,1)}${row("Swing length (ft)",b.sl,e.sl,2)}${row("Attack angle (\u00b0)",b.aa,e.aa,1)}${b.tilt!=null?row("Path tilt (\u00b0)",b.tilt,e.tilt,1):""}</table></div>
 <dl class="det"><dt>Bat path vs pitch</dt><dd title="${bandTip(b.sweet)}">${b.vba==null?"-":f1(b.vba)+"\u00b0"} <span class="${bd[1]}">${bd[0]}</span></dd>${b.ev!=null?`<dt>Contact</dt><dd>${f1(b.ev)} mph, ${b.la==null?"-":b.la+"\u00b0"}${b.xw!=null?", xwOBA "+b.xw.toFixed(3):""}</dd>`:""}</dl>`}
function forHim(q,hid){const d=q.dmg;if(!d)return "";const A=(G.arsenal[hid]||{}).avg_damage;
 return `<dt>Pitch for him</dt><dd title="Damage per swing: xwOBA on contact, zero for misses and fouls."><span class="${CATC[d.cat]}">${CATN[d.cat]}</span> <span class="mut">${FAMN[d.family]||d.family}, ${ZONEN[d.zone].toLowerCase()}: ${d.damage.toFixed(2)} per swing vs ${A==null?"-":A.toFixed(2)} avg (${d.n} swings)</span></dd>`}
function arsenalCard(hid,starterName){const a=G.arsenal[hid];if(!a)return "";
 const ed=x=>x.damage-x.league.damage,rows=a.types.map(x=>`<tr><td>${pname(x.type)}</td><td class="num">${pct(x.usage)}</td><td class="num">${f1(x.velo)}</td><td class="num">${x.n_swings}</td><td class="num">${pct(x.whiff)} <span class="mut">${pct(x.league.whiff)}</span></td><td class="num">${x.damage.toFixed(2)} <span class="mut">${x.league.damage.toFixed(2)}</span></td><td class="num ${ed(x)>.02?"lab-ok":ed(x)<-.02?"lab-bad":""}">${(ed(x)>=0?"+":"")+ed(x).toFixed(2)}</td><td class="num">${x.exp_vba==null?"-":f1(x.exp_vba)+"\u00b0"}</td><td title="${bandTip(a.sweet)}">${bandName(x.band,a.sweet)[0]}</td></tr>`).join("");
 const gr=Object.entries(a.groups).filter(([k,g])=>g.n>0).sort((p,q)=>q[1].idx-p[1].idx).map(([k,g])=>{const [fam,z]=k.split("|");return `<tr><td>${FAMN[fam]||fam}</td><td>${ZONEN[z]}</td><td class="num">${g.n}</td><td class="num">${g.damage.toFixed(2)} <span class="mut">${g.league.toFixed(2)}</span></td><td class="${CATC[g.cat]}">${CATN[g.cat]}</td></tr>`}).join("");
 return `<div class="card"><h3>Against ${starterName}</h3><div class="mut">${a.swings} tracked swings before this game. Average swing ${a.avg_damage.toFixed(2)} (league ${a.league_damage.toFixed(2)}).</div>
  ${curveSVG(a)}<div class="tw"><table><tr><th>Pitch</th><th class="num">Use</th><th class="num">Velo</th><th class="num">Swings</th><th class="num">Whiff <span class="mut">lg</span></th><th class="num">Damage <span class="mut">lg</span></th><th class="num">Edge</th><th class="num">Bat path</th><th>Plane fit</th></tr>${rows}</table></div>
 <details style="margin-top:var(--s2)"><summary>Where he damages</summary><div class="tw"><table><tr><th>Pitch group</th><th>Zone</th><th class="num">Swings</th><th class="num">Damage <span class="mut">lg</span></th><th>For him</th></tr>${gr}</table></div></details>
 <details style="margin-top:var(--s2)"><summary>Definitions</summary><p class="note">Damage: xwOBA on contact, counting zero for misses and fouls. Figures shrink toward the league (lg) when his sample is thin. Edge: his damage minus the league's. Bat path: his usual attack angle minus the pitch's approach angle.</p></details></div>`}
function decisionSummary(tot){let sw={damage:0,average:0,weak:0},tk=0;tot.forEach(p=>p.pitches.forEach(q=>{if(!q.dmg||/bunt|pitchout/.test(q.desc))return;if(q.swing)sw[q.dmg.cat]++;else if(q.dmg.cat==="damage")tk++}));return {sw,tk}}
function skipBox(p){const s=skipInfo(p);
 if(s.skipped)return `<div class="skipbar">Skipped: ${s.reason} (${s.by==="auto"?"automatic":"coach"}). ${SKIPMODE==="exclude"?"Excluded from":"Included in"} totals. <button data-incl="${p.id}" class="noprint">Include</button></div>`;
 return `<div class="logrow noprint"><select id="skipwhy" aria-label="Reason to skip">${SKIP_WHY.map(w=>`<option>${w}</option>`).join("")}</select><button data-skip="${p.id}">Skip at-bat</button>${s.overridden?`<span class="mut">Restored (flagged: ${s.reason}).</span>`:""}</div>`}
function paPanel(){const p=G.pas.find(x=>x.id===SELPA);if(!p)return "";
 const n=p.pitches.length;if(SELPITCH>=n)SELPITCH=0;const q=p.pitches[SELPITCH],pl=planOf(q),rv=review(q);
 const codes=q.plan&&q.plan.grid,deltas=q.plan&&q.plan.deltas,st=p.vs_starter?paStats(p):null;
 const chips=p.pitches.map((x,i)=>`<button class="sq k-${KIND(x.desc)} ${i===SELPITCH?"cur":""}" data-pi="${i}" title="Pitch ${x.n}: ${cap(x.desc)}">${x.n}</button>`).join("");
 const rows=p.pitches.map((x,i)=>{const l=planOf(x),r=review(x);return `<tr data-pr="${i}" class="${i===SELPITCH?"sel":""}"><td>${x.n}</td><td>${x.count}</td><td>${pname(x.type)}${x.velo?" "+x.velo.toFixed(0):""}</td><td>${where(x)}</td><td>${doWord(x)}, ${x.desc}</td><td>${l?callWord(l.call):"-"}</td><td class="num">${l&&l.dv!=null?sgn(l.dv):"-"}</td><td class="${r?r[1]:""}">${r?r[0]:""}</td></tr>`}).join("");
 return `<div class="card"><div class="head"><div><div class="mut">${p.half==="Top"?"Top":"Bottom"} ${p.inning} \u00b7 ${p.team}</div><div class="name">${p.batter_name} (${p.stand}) vs. ${p.pitcher_name}</div>
 <div><span class="chip">${p.result}</span> <span class="chip">${p.vs_starter?"Starter: plan applies":"Reliever: no plan"}</span></div></div>
 ${st?`<div class="stats" style="margin:0"><span>Decision value <b>${sgn(st.dv)}</b> runs</span><span><b>${st.bad}</b> below alternative</span></div>`:""}</div>${skipBox(p)}
 <div class="zonewrap"><div class="zonecol"><div class="zonecard">${zoneSVG(codes,deltas,{stand:p.stand,pitches:p.pitches,sel:SELPITCH,szTop:q.sz_top,szBot:q.sz_bot,showAll:SHOWALL})}
  <div class="legend"><span><i class="sw" style="background:${mix(.12)}"></i>Swing</span><span><i class="sw" style="background:${mix(-.12)}"></i>Take</span><span><i class="sw" style="background:var(--mid)"></i>No call</span><span>Outline: his zone</span></div>
  <div class="legend"><span><i class="dotk" style="background:var(--panel)"></i>Ball</span><span><i class="dotk" style="background:var(--k-called)"></i>Called strike</span><span><i class="dotk" style="background:var(--k-whiff)"></i>Swinging strike</span><span><i class="dotk" style="background:var(--k-foul)"></i>Foul</span><span><i class="dotk" style="background:var(--k-play)"></i>In play</span></div>
  <div class="seq noprint">${chips}</div>
  <div class="stepper noprint"><button data-step="-1">Previous</button><button data-step="1">Next</button><label class="f"><input type="checkbox" id="showall" ${SHOWALL?"checked":""}> All pitches</label></div></div></div>
  <div class="detcol"><p class="big">Pitch ${q.n} of ${n}: ${pname(q.type)}${q.velo?", "+q.velo.toFixed(1)+" mph":""}</p>
   <dl class="det"><dt>Count</dt><dd>${q.count}</dd><dt>Situation</dt><dd>${q.outs} out${q.outs===1?"":"s"}, ${basesText(q.bases)}, ${leadText(q.lead)}</dd><dt>Location</dt><dd>${where(q)}</dd>
   <dt>Plan</dt><dd>${pl?callWord(pl.call)+(pl.delta!=null?` <span class="mut" title="Swing minus take, in wOBA">(${sgn(pl.delta)})</span>`:""):"No plan (reliever)"}</dd><dt>Hitter</dt><dd>${doWord(q)}, ${q.desc}</dd>
   <dt>Value</dt><dd>${pl&&pl.dv!=null?sgn(pl.dv)+" runs":"Not scored"}${rv?` <span class="${rv[1]}">${rv[0]}</span>`:""}${pl&&pl.flags.includes("umpire_miss")&&pl.label!=="UMPIRE_MISS"?` <span class="mut">Umpire miss</span>`:""}</dd>${forHim(q,p.batter)}</dl>
   ${swingBox(q)}
   ${p.pitches.some(x=>x.plan&&x.plan.spot)?`<p class="note">Runner on third, under 2 outs: use the selector at the top to switch policy.</p>`:""}
   <div class="tw"><table style="margin-top:var(--s4)"><tr><th>#</th><th>Count</th><th>Pitch</th><th>Location</th><th>Hitter</th><th>Plan</th><th class="num">Value</th><th>Review</th></tr>${rows}</table></div></div></div>
 <div class="logrow noprint"><button data-hit="${p.batter}">Pregame: ${last(p.batter_name)}</button></div></div>`}
function gameView(){
 const inView=p=>TEAM==="all"||p.half===TEAM;const tot=G.pas.filter(p=>p.vs_starter&&inView(p)&&counted(p));const nSkip=G.pas.filter(p=>inView(p)&&skipInfo(p).skipped).length;
 let dv=0,bad=0,pn=0,silent=0;tot.forEach(p=>{const s=paStats(p);dv+=s.dv;bad+=s.bad;pn+=s.n;silent+=s.silent});const ds=decisionSummary(tot);
 const skipCtl=`<label class="f noprint">Skipped at-bats (${nSkip}) <select id="skipmode"><option value="exclude" ${SKIPMODE==="exclude"?"selected":""}>Excluded from totals</option><option value="include" ${SKIPMODE==="include"?"selected":""}>Included in totals</option></select></label>`;
 const tile=(l,v,tip)=>`<div class="tile" title="${tip}"><div class="tl">${l}</div><div class="tv">${v}</div></div>`;
 return `<div class="hero"><div class="hlab" title="Model value of the choices made versus the alternatives, in runs">Decision value against the starters</div><div class="hnum">${sgn(dv)}<small>runs</small></div>
 <div class="hrow"><span class="delta ${bad>0?"dn":""}">${bad} choices below the alternative</span><span class="hlab">${tot.length} plate appearances</span></div>
 <div class="tiles">${tile("Plan gives a call",pct(pn?(pn-silent)/pn:0),"Share of pitches with a swing or take call. The plan stays silent when evidence is thin or the options are close.")}${tile("Swings at damage pitches",ds.sw.damage,"Swings at pitch groups the hitter damages")}${tile("Swings at average pitches",ds.sw.average,"Swings at pitch groups near his average")}${tile("Swings at weak spots",ds.sw.weak,"Swings at pitch groups where he does little damage")}${tile("Damage pitches taken",ds.tk,"Pitches in his damage groups that he took")}</div>
 <div class="hrow" style="margin-top:var(--s4)">${skipCtl}</div></div>
 <div class="card" style="margin-top:var(--s4)">${innings()}<p class="note">Click a plate appearance. Faded: reliever, no plan. Dashed: skipped.</p></div><div style="margin-top:var(--s4)">${paPanel()}</div>`}
/* ---------------- pregame board ---------------- */
const NAME={VALUE:"Value plan",CONTACT:"Contact-capped",HUNT:"Hunt a spot"};
const DESC={VALUE:"Swing where swinging beats taking.",CONTACT:"Fewer swings that miss; adds near-even contact swings.",HUNT:"Sit on one pitch type. Experimental: the model cannot value anticipation."};
function viable(cn){return cn.differ.VALUE_vs_CONTACT>=0.05&&(cn.styles.CONTACT.value_per_100-cn.styles.VALUE.value_per_100)>=-0.5}
const BOARDS={};
async function ensureBoard(h){if(!SERVER||BOARDS[h.id]==="loading")return;BOARDS[h.id]="loading";
 try{const r=await fetch(`/api/board/${G.game_pk}/${h.id}`);if(r.ok){Object.assign(h,await r.json());delete h.pending;BOARDS[h.id]="done";if(VIEW==="board")render();return}}catch(e){}
 BOARDS[h.id]=null;setTimeout(()=>{if(VIEW==="board"&&h.pending)ensureBoard(h)},5000)}
const hitterSelect=()=>`<select id="bh" aria-label="Hitter">${["Top","Bot"].map(hf=>side(hf).board.hitters.map((x,i)=>`<option value="${hf}|${i}" ${hf===HALF&&i===HI?"selected":""}>${hf==="Top"?G.away:G.home}: ${x.order}. ${x.name}</option>`).join("")).join("")}</select>`;
function boardView(){const sd=side(HALF),B=sd.board;if(HI>=B.hitters.length)HI=0;const h=B.hitters[HI];
 if(h.pending){ensureBoard(h);return `<div class="top"><label class="mut">Hitter: ${hitterSelect()}</label></div><div class="card" style="margin-top:var(--s4)"><h3>${h.name}</h3><p class="mut">The pregame board is still being built. It appears here as soon as it is ready.</p></div>`}
 const cn=h.tto[TTO][CNT];
 const types=Object.keys(cn.arsenal).sort((a,b)=>cn.arsenal[b].usage-cn.arsenal[a].usage);if(!PT||!types.includes(PT))PT=types[0];
 const sel=`<select id="bh">${["Top","Bot"].map(hf=>side(hf).board.hitters.map((x,i)=>`<option value="${hf}|${i}" ${hf===HALF&&i===HI?"selected":""}>${hf==="Top"?G.away:G.home}: ${x.order}. ${x.name}</option>`).join("")).join("")}</select>`;
 const ars=Object.entries(B.starter.arsenal_tto1_0_0).sort((a,b)=>b[1].usage-a[1].usage).map(([k,v])=>`<tr><td>${pname(k)}</td><td class="num">${pct(v.usage)}</td><td class="num">${v.velo.toFixed(1)}</td><td class="num">${v.ivb.toFixed(1)}</td><td class="num">${v.hb.toFixed(1)}</td></tr>`).join("");
 const tabs=["1","2","3"].map(t=>`<button class="${t===TTO?"on":""}" data-tto="${t}">${t==="1"?"1st time":t==="2"?"2nd time":"3rd+ time"}</button>`).join("");
 let cnts="";for(let s=0;s<3;s++)for(let b=0;b<4;b++){const k=b+"-"+s;cnts+=`<button class="${k===CNT?"on":""}" data-c="${k}">${k}</button>`}
 const chips=types.map(t=>`<button class="${t===PT?"on":""}" data-pt="${t}">${t} ${pct(cn.arsenal[t].usage)}</button>`).join("");
 const show=["VALUE"].concat(viable(cn)?["CONTACT"]:[]).concat(EXP?["HUNT"]:[]);
 const key=[G.date,sd.starter,h.id,TTO,CNT].join("|");const cur=(LOG[key]||{}).path;
 const card=st=>{const s=cn.styles[st];const diff=st==="CONTACT"?cn.differ.VALUE_vs_CONTACT:st==="HUNT"?cn.differ.VALUE_vs_HUNT:null;
  return `<div class="card ${cur===st?"chosen":""}"><h3>${NAME[st]}${st==="HUNT"?" (experimental)":""}</h3><div>${s.tags.map(t=>`<span class="chip">${t}</span>`).join("")}</div>${s.target?`<div class="mut">Hunt: ${s.target}</div>`:""}
  ${zoneSVG(s.cells[PT],cn.delta[PT],{small:true,stand:h.stand,szTop:3.5,szBot:1.5})}<div class="mut">${DESC[st]}</div>${st==="CONTACT"&&s.value_per_100>cn.styles.VALUE.value_per_100?`<div class="mut">Higher than the value plan because it also swings at near-even cells the value plan leaves open. Less certain.</div>`:""}
  <table style="margin-top:6px"><tr><td>Swing on</td><td class="num">${pct(s.swing_share)} of his pitches</td></tr><tr><td>Whiff on swings</td><td class="num">${pct(s.whiff)}</td></tr><tr><td>xwOBA on contact</td><td class="num">${s.contact.toFixed(3)}</td></tr>
  <tr><td>Value if followed</td><td class="num">${sgn(s.value_per_100)} runs / 100 pitches</td></tr>${diff==null?"":`<tr><td>Differs from value plan</td><td class="num">${pct(diff)} of pitches</td></tr>`}</table>
  <div class="logrow noprint"><button data-pick="${st}">Use this plan</button></div></div>`};
 const styles=show.map(card).join("")+(show.length===1?`<div class="card"><h3>One viable plan here</h3><div class="mut">${CNT.endsWith("-2")?"Two strikes: protect the plate.":cn.styles.VALUE.swing_share===0?"No pitch is worth swinging at in this count.":"The alternative plan differs on under 5% of pitches or costs over half a run per 100."}</div></div>`:"");
 const L=LOG[key]||{};
 const logBox=`<div class="card noprint" style="margin-top:12px"><h3>Your call: ${h.name}, ${CNT}, ${TTO==='1'?'1st':TTO==='2'?'2nd':'3rd+'} time through</h3><div class="logrow"><select id="lg-path"><option value="">Plan chosen</option><option value="VALUE">Value plan</option><option value="CONTACT">Contact-capped</option><option value="OWN">My own plan</option></select>
  <select id="lg-why"><option value="">Reason</option><option>hitter feel/recent form</option><option>scouting report</option><option>game situation</option><option>development goal</option><option>model looks wrong</option><option>other</option></select><input type="text" id="lg-note" placeholder="note" size="28"><button id="lg-save">Save</button></div></div>`;
 const tg=(h.targets.groups||[]).map(g=>`<li>${FAMN[g.family]||g.family}, ${g.zone} zone, ${g.count}: ${g.his_rate.toFixed(1)} runs lost per 100 vs. ${g.typical_rate.toFixed(1)} typical (${g.n} pitches)</li>`).join("")||"<li class='mut'>not enough tracked pitches</li>";
 return `<div class="top"><label class="mut">Hitter: ${sel}</label></div>
 <div class="two"><div class="card"><h3>${B.starter.name}</h3><div class="mut">${B.starter.starts_before} earlier starts</div><table><tr><th>Pitch</th><th class="num">Use at 0-0</th><th class="num">Velo</th><th class="num">IVB (in)</th><th class="num">HB (in)</th></tr>${ars}</table></div>
 <div class="card"><h3>${h.order}. ${h.name} (${h.stand}) <span class="chip">${cap(h.profile.support)} support, ${h.profile.swings} swings</span></h3><div class="mut">Whiff ${h.profile.whiff==null?"-":pct(h.profile.whiff)} (league ${pct(h.profile.league_whiff)}), xwOBA on contact ${h.profile.xwobacon==null?"-":h.profile.xwobacon.toFixed(3)} (league ${h.profile.league_xwobacon.toFixed(3)})</div><ul>${tg}</ul><div class="note">Development targets: where his choices cost more than a typical hitter's.</div></div></div>
 ${arsenalCard(h.id,B.starter.name)}
 <div class="card" style="margin-top:12px"><div class="tabs">${tabs}</div><div class="counts">${cnts}</div><div class="tabs">${chips}</div><div><label class="mut"><input type="checkbox" id="exp" ${EXP?"checked":""}> Show experimental hunt plan</label></div>
 <div class="mut">${h.name} vs. ${B.starter.name}\u2019s ${pname(PT)}, ${CNT}, ${TTO==="1"?"1st":TTO==="2"?"2nd":"3rd+"} time through. Blue: swing. Coral: take. Gray: no call. Outline: typical zone.</div><div class="styles">${styles}</div></div>${logBox}`}
function swingCard(h){const sw=G.swing_profiles[h];if(!sw||!sw.bat_speed)return "<div class='mut'>No bat-tracking profile.</div>";const f=(t,k,d=1)=>sw[t]?sw[t][k].toFixed(d):"-";
 return `<table><tr><th></th><th>His</th><th>League</th></tr><tr><td>Bat speed, middle pitch (mph)</td><td class="num">${f("bat_speed","mid")}</td><td class="num">${f("bat_speed","league_mid")}</td></tr>
 <tr><td>Bat speed, two strikes (mph)</td><td class="num">${f("bat_speed","mid_two_strikes")}</td><td class="num">-</td></tr><tr><td>Swing length (ft)</td><td class="num">${f("swing_length","mid",2)}</td><td class="num">${f("swing_length","league_mid",2)}</td></tr>
 <tr><td>Attack angle low / middle / high pitch (deg)</td><td class="num">${f("attack_angle","low")} / ${f("attack_angle","mid")} / ${f("attack_angle","high")}</td><td class="num">${f("attack_angle","league_mid")} (mid)</td></tr>
 ${sw.tilt?`<tr><td>Swing path tilt, middle pitch (deg)</td><td class="num">${f("tilt","mid")}</td><td class="num">${f("tilt","league_mid")}</td></tr>`:""}</table><div class="note">From ${sw.bat_speed.n} tracked swings; ${(sw.bat_speed.kept*100).toFixed(0)}% of his own pattern is kept, the rest is the league average. Descriptive: not used in the plan yet.</div>`}
let HSEL=null;
function hittersView(){const ids=[];G.pas.forEach(p=>{if(!ids.some(x=>x.id===p.batter))ids.push({id:p.batter,name:p.batter_name,half:p.half})});if(!HSEL)HSEL=ids[0].id;
 const opts=ids.map(x=>`<option value="${x.id}" ${x.id===HSEL?"selected":""}>${x.half==="Top"?G.away:G.home}: ${x.name}</option>`).join("");const mine=G.pas.filter(p=>p.batter===HSEL);
 const rows=mine.map(p=>`<tr class="hp" data-pa="${p.id}" style="cursor:pointer"><td>${p.inning}${p.half==="Top"?"T":"B"}</td><td>${p.pitcher_name}${p.vs_starter?"":" (reliever)"}</td><td>${p.result}</td><td class="num">${!p.vs_starter?"-":skipInfo(p).skipped?"Skipped":sgn(paStats(p).dv)}</td><td class="num">${!p.vs_starter?"-":skipInfo(p).skipped?(skipInfo(p).reason):paStats(p).bad}</td></tr>`).join("");
 return `<div class="top"><label class="mut">Hitter: <select id="hs">${opts}</select></label></div><div class="two"><div class="card"><h3>Swing profile</h3>${swingCard(HSEL)}</div><div class="card"><h3>This game</h3><table><tr><th>Inning</th><th>Pitcher</th><th>Result</th><th>Decision value</th><th>Worse than other option</th></tr>${rows}</table><div class="note">Click a row to see the pitches.</div></div></div>${arsenalCard(HSEL,G.sides[(G.pas.find(x=>x.batter===HSEL)||{half:"Top"}).half].starter_name)}`}
function logView(){const rows=Object.values(LOG).sort((a,b)=>(b.saved||"").localeCompare(a.saved||"")).map(r=>`<tr><td>${r.hitter}</td><td>${r.tto}</td><td>${r.count}</td><td>${r.path||""}</td><td>${r.why||""}</td><td>${r.note||""}</td></tr>`).join("");
 return `<div class="card"><h3>Coach decisions saved on this device</h3><table><tr><th>Hitter</th><th>TTO</th><th>Count</th><th>Plan</th><th>Reason</th><th>Note</th></tr>${rows||"<tr><td colspan=6 class='mut'>Nothing saved yet. Choose a plan on the pregame board.</td></tr>"}</table><div class="logrow"><button id="lg-export">Export CSV</button></div></div>`}
function wire(){
 document.querySelectorAll("[data-pa]").forEach(e=>e.onclick=()=>{SELPA=+e.dataset.pa;SELPITCH=0;VIEW="game";render()});
 document.querySelectorAll("[data-pi]").forEach(e=>e.onclick=()=>{SELPITCH=+e.dataset.pi;render()});
 document.querySelectorAll("[data-pr]").forEach(e=>e.onclick=()=>{SELPITCH=+e.dataset.pr;render()});
 document.querySelectorAll("[data-step]").forEach(e=>e.onclick=()=>step(+e.dataset.step));
 document.querySelectorAll("[data-skip]").forEach(b=>b.onclick=()=>{const p=G.pas.find(x=>x.id===+b.dataset.skip);LOG[skipKey(p)]={date:G.date,starter:"",hitter:p.batter_name,hitter_id:p.batter,tto:"",count:"",offered:"",path:"SKIP",why:$("#skipwhy").value,note:"At-bat "+p.id+": "+p.result,saved:new Date().toISOString()};saveLog();render()});
 document.querySelectorAll("[data-incl]").forEach(b=>b.onclick=()=>{const p=G.pas.find(x=>x.id===+b.dataset.incl);LOG[skipKey(p)]={date:G.date,starter:"",hitter:p.batter_name,hitter_id:p.batter,tto:"",count:"",offered:"",path:"INCLUDE",why:"Restored by coach",note:"At-bat "+p.id+": "+p.result,saved:new Date().toISOString()};saveLog();render()});
 const sm=$("#skipmode");if(sm)sm.onchange=()=>{SKIPMODE=sm.value;render()};
 const sa=$("#showall");if(sa)sa.onchange=()=>{SHOWALL=sa.checked;render()};
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
document.addEventListener("keydown",e=>{if(VIEW!=="game"||["INPUT","SELECT","TEXTAREA"].includes(document.activeElement.tagName))return;if(e.key==="ArrowRight")step(1);else if(e.key==="ArrowLeft")step(-1)});
/* ---------------- game library (server mode) ---------------- */
let LIB={games:[],ready:false,date:"",q:"",built:false,msg:"",poll:null};
async function loadLib(){try{const r=await (await fetch("/api/games")).json();LIB.games=r.games;LIB.ready=r.ready;if(!LIB.date){const b=LIB.games.find(g=>g.status==="ready");LIB.date=(b||LIB.games[0]||{}).date||""}}catch(e){LIB.msg="Cannot reach the GamePlan server."}
 clearTimeout(LIB.poll);if(VIEW==="library"&&(!LIB.ready||LIB.games.some(g=>g.status==="building")))LIB.poll=setTimeout(async()=>{await loadLib();if(VIEW==="library")render()},4000)}
function gameNo(g){const same=LIB.games.filter(x=>x.date===g.date&&x.home===g.home&&x.away===g.away).sort((a,b)=>a.game_pk-b.game_pk);return same.length>1?` (game ${same.findIndex(x=>x.game_pk===g.game_pk)+1})`:""}
function libraryView(){const q=LIB.q.toLowerCase(),dates=[...new Set(LIB.games.map(g=>g.date))];
 const rows=LIB.games.filter(g=>(!LIB.date||g.date===LIB.date)&&(!LIB.built||g.status==="ready")&&(!q||[g.away,g.home,g.away_starter,g.home_starter].join(" ").toLowerCase().includes(q)));
 const nReady=LIB.games.filter(g=>g.status==="ready").length;
 const btn=g=>g.status==="ready"?`${g.boards_running?`<span class="chip" title="Pregame boards fill in one hitter at a time">Boards loading (${g.boards_done})</span> `:""}<button data-open="${g.game_pk}">Open</button>`:g.status==="building"?`<span class="chip">Building</span>`:`<button data-build="${g.game_pk}">${g.status==="failed"?"Retry build":"Build"}</button>`;
 return `<div class="hero"><div class="hlab">Game library</div><div class="hnum">${nReady}<small>built of ${LIB.games.length} games</small></div>
 <div class="hrow noprint"><label class="f">Date <select id="libdate"><option value="">All dates</option>${dates.map(d=>`<option value="${d}" ${d===LIB.date?"selected":""}>${d}</option>`).join("")}</select></label>
 <label class="f">Search <input type="text" id="libq" value="${LIB.q.replace(/"/g,"")}" placeholder="Team or pitcher"></label><label class="f"><input type="checkbox" id="libbuilt" ${LIB.built?"checked":""}> Built only</label></div>
 ${LIB.ready?"":`<p class="hlab">Reading game files...</p>`}${LIB.ready&&!LIB.games.length?dlBox():""}${LIB.msg?`<p class="hlab">${LIB.msg}</p>`:""}</div>
 <div class="card" style="margin-top:var(--s4)">${rows.length?rows.map(g=>`<div class="grow"><div><div class="name" style="font-size:var(--t-lead)">${g.away||"?"} at ${g.home||"?"}${gameNo(g)}</div><div class="mut">${g.date} \u00b7 ${g.away_starter||"?"} vs. ${g.home_starter||"?"} \u00b7 ${g.pas} plate appearances</div></div><div>${btn(g)}</div></div>`).join(""):`<p class="mut">${LIB.ready?"No games match.":"The list appears when the data has been read."}</p>`}
 <p class="note">Building a game takes about 5 minutes; each hitter's pregame board then fills in over the next few. You can build up to 2 at a time and keep working.</p></div>`}
let DL={running:false,files:0,total:195};
function dlBox(){return DL.running?`<p class="hlab">Downloading the 2025 season: ${DL.files} of ${DL.total} days...</p>`:`<p class="hlab">No game data yet. The 2025 season is about 200 MB and takes 10 to 20 minutes to download.</p><div class="hrow noprint"><button data-dl>Download the 2025 season</button></div>`}
async function pollDl(){try{DL=await (await fetch("/api/download")).json()}catch(e){return}if(DL.running){if(VIEW==="library")render();setTimeout(pollDl,4000)}else{await loadLib();if(VIEW==="library")render()}}
function wireLib(){document.querySelectorAll("[data-dl]").forEach(b=>b.onclick=async()=>{b.disabled=true;await fetch("/api/download",{method:"POST"});pollDl()});const d=$("#libdate");if(!d)return;d.onchange=()=>{LIB.date=d.value;render()};$("#libq").oninput=e=>{LIB.q=e.target.value;const p=e.target.selectionStart;render();const n=$("#libq");n.focus();n.setSelectionRange(p,p)};$("#libbuilt").onchange=e=>{LIB.built=e.target.checked;render()};
 document.querySelectorAll("[data-open]").forEach(b=>b.onclick=()=>{location.hash="#/game/"+b.dataset.open});
 document.querySelectorAll("[data-build]").forEach(b=>b.onclick=async()=>{b.disabled=true;const r=await fetch("/api/build",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({game_pk:b.dataset.build})});const j=await r.json();LIB.msg=r.ok?"":(j.error||"Build failed to start.");await loadLib();render()})}
function render(){const lib=VIEW==="library";document.querySelector(".tools").hidden=lib;document.querySelectorAll("[data-v]").forEach(b=>b.classList.toggle("on",b.dataset.v===VIEW));
 if(lib){$("#title").textContent="GamePlan";$("#main").innerHTML=libraryView();wireLib();return}
 $("#main").innerHTML=VIEW==="game"?gameView():VIEW==="board"?boardView():VIEW==="hitters"?hittersView():logView();wire()}
async function route(){
 if(!SERVER){initGame(EMBED);VIEW="game";buildTabs();render();return}
 const m=location.hash.match(/^#\/game\/(\d+)/);
 if(m){$("#main").innerHTML=`<div class="card"><p class="mut">Loading game...</p></div>`;const r=await fetch("/api/game/"+m[1]);
  if(r.ok){initGame(await r.json());VIEW="game";buildTabs();render();return}LIB.msg="That game is not built yet."}
 VIEW="library";buildTabs();render();await loadLib();if(VIEW==="library")render()}
window.addEventListener("hashchange",route);
loadLog().then(route);
