"""How closely a pitch rebuilt from release point and break matches Savant's own path. Needs the league files (data/league, not in git).

  PYTHONPATH=src python3 qa/import_validation.py

Result on 2026-10-10, 5,970 random 2025 pitches: 5,959 pass the draw checks; against Statcast's own velocity and acceleration the path is off by a median 0.09 ft,
90th percentile 0.22 ft, 99th 0.37 ft, worst 0.56 ft, measured a quarter, half and three quarters of the way to the plate.
"""
import csv,glob,math,statistics as st,random,sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))
from gameplan import simview
from gameplan.engine import pitchimport as PI
rnd=random.Random(5); rows=[]
for f in sorted(glob.glob(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "league" / "2025-*.csv")))[::9]:
    rows+= [r for r in csv.DictReader(open(f))]
rnd.shuffle(rows)
ok=bad=0; devs=[]; reasons={}; speeddiff=[]
for r in rows[:6000]:
    try:
        v={k:float(r[k]) for k in ("release_speed","release_pos_x","release_pos_z","release_extension","plate_x","plate_z","pfx_x","pfx_z","vx0","vy0","vz0","ax","ay","az","sz_top","sz_bot")}
    except: continue
    ph=PI.reconstruct(v["release_pos_x"],v["release_pos_z"],v["release_extension"],v["release_speed"],v["plate_x"],v["plate_z"],v["pfx_x"],v["pfx_z"])
    if ph is None: bad+=1; reasons["noreconstruct"]=reasons.get("noreconstruct",0)+1; continue
    feed=dict(ph,px=v["plate_x"],pz=v["plate_z"],sz_top=v["sz_top"],sz_bot=v["sz_bot"],start_speed=v["release_speed"])
    par,why=simview.sim_params(feed)
    if par is None:
        bad+=1; k=why.split(" ")[0]+" "+why.split(" ")[1]; reasons[k]=reasons.get(k,0)+1; continue
    ok+=1
    tt=simview.t_to_plane(ph); 
    dev=0
    for fr in (0.25,0.5,0.75):
        t=tt*fr
        dx=(ph["vx0"]-v["vx0"])*t+0.5*(ph["ax"]-v["ax"])*t*t
        dy=(ph["vy0"]-v["vy0"])*t+0.5*(ph["ay"]-v["ay"])*t*t
        dz=(ph["vz0"]-v["vz0"])*t+0.5*(ph["az"]-v["az"])*t*t
        dev=max(dev,math.sqrt(dx*dx+dy*dy+dz*dz))
    devs.append(dev)
print("rows",ok+bad,"pass gates",ok,"fail",bad,reasons)
devs.sort(); print("max path deviation (ft): median %.3f p90 %.3f p99 %.3f max %.3f"%(devs[len(devs)//2],devs[int(len(devs)*.9)],devs[int(len(devs)*.99)],devs[-1]))
