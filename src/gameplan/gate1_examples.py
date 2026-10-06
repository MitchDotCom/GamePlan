"""Gate 1 (docs/GAMEPLAN_V2_PLAN.md section 7): worked examples on real 2025 games, for the owner and a coach to judge.

For a hitter-start: the card (his two calls against that starter, using only earlier games), the receipt for that game (how he handled the
call pitches), and the card for his next start with last night's receipt on top. Working definition: pitch type by height in his own zone
(S3 from docs/GATE0_READOUT.md). Calls rank the starter's pitches by usage x the hitter's earlier loss on them, shrunk toward the league (path P);
one take call and one attack call. Examples are chosen by a fixed seed from September 2025 so they cannot be cherry-picked.

    python -m gameplan.gate1_examples --league data/league --out docs/GATE1_WORKED_EXAMPLES.md"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import pathlib
import random
from collections import defaultdict

import numpy as np

from .mockup import _flip, pitcher_name
from .recognition_paths import K_SHRINK, build_cells, load, referee
from .shape import ContactModel
from .zone import CalledStrikeModel

NAMES = {"FF": "four-seam fastball", "SI": "sinker", "FC": "cutter", "SL": "slider", "ST": "sweeper", "CU": "curveball", "KC": "knuckle-curve",
         "CH": "changeup", "FS": "splitter", "SV": "slurve", "CS": "slow curve", "FO": "forkball", "KN": "knuckleball", "EP": "eephus", "SC": "screwball"}
THIRD = ["low", "middle", "high"]
SEED = 2025
MIN_HIST = 300


def names_and_teams(league_dir: str):
    bname, team = {}, {}
    for f in sorted(glob.glob(str(pathlib.Path(league_dir) / "*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            b = r["batter"]
            bname.setdefault(b, _flip(r.get("player_name", "")))
            team[(r["game_pk"], b)] = r["away_team"] if r["inning_topbot"] == "Top" else r["home_team"]
    return bname, team


def cell_label(cell, tcode_names):
    return f"{NAMES.get(tcode_names[cell // 3], tcode_names[cell // 3])}, {THIRD[cell % 3]} in his zone"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-arizona", type=int, default=10)
    ap.add_argument("--n-other", type=int, default=5)
    a = ap.parse_args(argv)
    rows, early, starters = load(a.league)
    ok = lambda s: s.x_away is not None and s.z is not None and None not in (s.velo, s.ivb, s.hb, s.vaa)
    league = ContactModel([], [s for s in rows if s.swing and ok(s)], mode="shapecount")
    zone = CalledStrikeModel([s for s in rows if not s.swing])
    P = [s for s in rows if (s.game_pk, s.pitcher) in starters and ok(s) and (s.game_pk, s.at_bat, s.pitch_no) in early]
    P.sort(key=lambda s: (s.date, s.game_pk, s.at_bat, s.pitch_no))
    loss, delta = [], []
    for i in range(0, len(P), 40000):
        l, d = referee(league, zone, P[i:i + 40000])
        loss.append(l)
        delta.append(d)
    loss, delta = np.concatenate(loss), np.concatenate(delta)
    cells, ncell, isfb, fam, zr = build_cells(P)
    c3 = cells["S3"]
    types = sorted({s.pitch_type for s in P})
    bname, team = names_and_teams(a.league)
    dates = np.array([s.date for s in P])
    game = np.array([s.game_pk for s in P])
    pit = np.array([s.pitcher for s in P])
    bat = np.array([s.batter for s in P])
    swing = np.array([s.swing for s in P])
    whiff = np.array([bool(s.whiff) for s in P])
    xw = np.array([s.xwoba if s.xwoba is not None else np.nan for s in P])
    nc = ncell["S3"]
    pcache = str(pathlib.Path(a.league).parent / "pitcher_names_2025.csv")

    def card(b, p, day, personal=True):
        before = dates < day
        L = np.bincount(c3[before], minlength=nc).astype(float)
        Ls = np.bincount(c3[before], weights=loss[before], minlength=nc)
        Ld = np.bincount(c3[before], weights=delta[before], minlength=nc)
        gm = Ls.sum() / L.sum()
        Lm = np.where(L > 0, Ls / np.maximum(L, 1), gm)
        Dm = np.where(L > 0, Ld / np.maximum(L, 1), 0.0)
        hm = before & (bat == b)
        hn = np.bincount(c3[hm], minlength=nc).astype(float)
        hs = np.bincount(c3[hm], weights=loss[hm], minlength=nc)
        Hm = (hs + K_SHRINK * Lm) / (hn + K_SHRINK) if personal else Lm
        sm = before & (pit == p)
        sn = np.bincount(c3[sm], minlength=nc).astype(float)
        usage = sn / max(sn.sum(), 1)
        take = Dm < 0
        calls = []
        for want_take in (True, False):
            sc = np.where((take == want_take) & (usage > 0), usage * Hm, -np.inf)
            j = int(np.argmax(sc))
            if np.isfinite(sc[j]):
                calls.append((want_take, j))
        info = []
        for want_take, j in calls:
            m = sm & (c3 == j)
            sw_h = swing[hm & (c3 == j)]
            sw_l = swing[before & (c3 == j)]
            info.append({"take": want_take, "cell": j, "usage": usage[j], "velo": float(np.mean([P[i].velo for i in np.where(m)[0]])),
                         "ivb": float(np.mean([P[i].ivb for i in np.where(m)[0]])), "hb": float(np.mean([P[i].hb for i in np.where(m)[0]])),
                         "his_loss": Hm[j] * 100, "lg_loss": Lm[j] * 100, "his_n": int(hn[j]),
                         "his_swing": float(sw_h.mean()) if len(sw_h) else float("nan"), "lg_swing": float(sw_l.mean())})
        return info, int(sn.sum() / max(1, len(set(game[sm]))))

    def receipt(b, p, day, g, info):
        out = []
        for c in info:
            m = (game == g) & (bat == b) & (pit == p) & (c3 == c["cell"])
            n = int(m.sum())
            sw = int((m & swing).sum())
            wh = int((m & whiff).sum())
            cq = xw[m & swing]
            cq = cq[~np.isnan(cq)]
            followed = (n - sw) if c["take"] else sw
            # rolling: his earlier games against any starter on the same pitch type and height
            r = (bat == b) & (dates < day) & (c3 == c["cell"])
            rn, rsw = int(r.sum()), int((r & swing).sum())
            rfollow = (rn - rsw) if c["take"] else rsw
            out.append({"n": n, "swings": sw, "whiffs": wh, "followed": followed, "cq": float(cq.mean()) if len(cq) else float("nan"),
                        "roll_n": rn, "roll_followed": rfollow})
        return out

    # fixed-seed selection of hitter-starts from September 2025
    groups = defaultdict(list)
    for i in range(len(P)):
        if dates[i] >= "2025-09-01":
            groups[(dates[i], game[i], pit[i], bat[i])].append(i)
    hist = defaultdict(int)
    for b in bat:
        hist[b] += 1
    az = [k for k in groups if team.get((k[1], k[3])) == "AZ" and len(groups[k]) >= 8 and hist[k[3]] >= 600]
    other = [k for k in groups if team.get((k[1], k[3])) != "AZ" and len(groups[k]) >= 8 and hist[k[3]] >= 600]
    rng = random.Random(SEED)
    picked, seen = [], set()
    for pool, n in ((sorted(az), a.n_arizona), (sorted(other), a.n_other)):
        rng.shuffle(pool)
        got = 0
        for k in pool:
            if k[3] in seen:
                continue
            picked.append((k, True))
            seen.add(k[3])
            got += 1
            if got >= n:
                break
    sample = sorted(k for k in groups if len(groups[k]) >= 8 and hist[k[3]] >= 600)
    random.Random(SEED + 1).shuffle(sample)
    same = tot = 0
    for k in sample[:250]:
        info_p, _ = card(k[3], k[2], k[0], True)
        info_l, _ = card(k[3], k[2], k[0], False)
        if info_p and info_l:
            tot += 1
            same += {(c["take"], c["cell"]) for c in info_p} == {(c["take"], c["cell"]) for c in info_l}
    out = ["# Gate 1 worked examples (2025 games, generated, not hand-picked)", "",
           "Each example is a real hitter-start. The card uses only games before that date. The receipt is how he handled the call pitches that night. "
           "The next card is for his next start, with the receipt on top. Judge one thing: **do these two calls make baseball sense for this hitter against this starter?**", "",
           f"Selection: fixed seed {SEED}, September 2025 starts, hitters with at least 600 earlier pitches seen against starters, one example per hitter; "
           f"{sum(1 for k, _ in picked if team.get((k[1], k[3])) == 'AZ')} Diamondbacks hitters (code AZ) and {sum(1 for k, _ in picked if team.get((k[1], k[3])) != 'AZ')} others (asked for {a.n_arizona} and {a.n_other}).", "",
           f"How personal are the calls? Across {tot} September hitter-starts picked at random, {same / max(tot, 1) * 100:.0f}% got exactly the same two calls as the starter-level ranking "
           "(the same two for every hitter against that starter). The rest differ in at least one call because of the hitter's own history.", "",
           "Definitions: a *take call* is a pitch type and height where the average-hitter model says taking is usually the better choice and this hitter has lost the most "
           "by swinging; an *attack call* is the opposite. Heights are thirds of his own zone (pitches outside the zone count in the nearest third). 'Loss' is runs per 100 pitches "
           "against the better option under the average-hitter model.", ""]
    for n, (k, is_az) in enumerate(picked, 1):
        day, g, p, b = k
        info, per_start = card(b, p, day)
        rc = receipt(b, p, day, g, info)
        later = sorted({(dates[i], game[i], pit[i]) for i in range(len(P)) if bat[i] == b and dates[i] > day})
        out.append(f"## {n}. {bname.get(b, b)} ({team.get((g, b), '?')}) vs {pitcher_name(pcache, p)}, {day}")
        out.append("")
        out.append(f"**Card.** The starter's pitches in earlier starts: about {per_start} per start seen by his lineup.")
        for c in info:
            kind = "TAKE" if c["take"] else "ATTACK"
            out.append(f"- **{kind}: {cell_label(c['cell'], types)}.** He throws it {c['usage'] * 100:.0f}% of the time ({c['velo']:.0f} mph, {c['ivb']:+.0f} in vertical, {c['hb']:+.0f} in horizontal break). "
                       f"The hitter has lost {c['his_loss']:.1f} runs per 100 on it (league {c['lg_loss']:.1f}); he swings {c['his_swing'] * 100:.0f}% of the time (league {c['lg_swing'] * 100:.0f}%), "
                       f"{c['his_n']} earlier pitches of his own.")
        out.append("")
        out.append("**Receipt (that night).**")
        for c, r in zip(info, rc):
            kind = "TAKE" if c["take"] else "ATTACK"
            word = "took" if c["take"] else "swung at"
            out.append(f"- {kind} call: saw {r['n']}, {word} {r['followed']}; swings {r['swings']}, whiffs {r['whiffs']}"
                       + (f", contact quality {r['cq']:.3f} xwOBA" if not np.isnan(r["cq"]) else "") + f". Season to date (earlier games): {word} {r['roll_followed']} of {r['roll_n']}.")
        if later:
            d2, g2, p2 = later[0]
            info2, _ = card(b, p2, d2)
            out.append("")
            out.append(f"**Next card ({d2}, vs {pitcher_name(pcache, p2)}).**")
            if not info2:
                out.append("- No card: this starter has no earlier starts in the data, so there is nothing to base the calls on.")
            for c in info2:
                kind = "TAKE" if c["take"] else "ATTACK"
                same = any(c["cell"] == c0["cell"] and c["take"] == c0["take"] for c0 in info)
                out.append(f"- {kind}: {cell_label(c['cell'], types)} ({'same as last night' if same else 'new'}).")
        out.append("")
    pathlib.Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {a.out} with {len(picked)} examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
