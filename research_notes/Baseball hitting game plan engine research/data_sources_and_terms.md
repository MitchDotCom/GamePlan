# Source inventory of data providers for a baseball analytics engine, with terms of use and organization-use verdicts

Research date 2026-10-01. Nothing here is legal advice; the club's counsel should confirm. Only sources readable in this environment were verified; see Gaps.

## Which sources can a for-profit club use operationally, and what do they provide?

### Takeaway
Public MLB sources (Savant, Stats API) are the only way to get Statcast-grade and Single-A data, but their governing terms permit only individual, non-commercial, non-bulk use without written MLBAM authorization, so they are proof-of-concept only until the club obtains that authorization or MLB-provided feeds. Clearly commercial-safe open sources are Retrosheet (attribution), Chadwick Register (ODC-By), and MIT-licensed client code. Eight otherwise-viable sources were omitted for license reasons.

### Cited Findings

Inventory table (verdict column = may a for-profit club use it operationally?)

| Source | Content | Coverage | Access / cost | Terms as found | Verdict | Quality / ingestion |
|---|---|---|---|---|---|---|
| Baseball Savant Statcast Search (MLB) | Pitch-level CSV, 80+ fields: velocity, release, spin, movement, batted ball, xStats, run/win expectancy, fielders, bat tracking (attack angle, swing path tilt, intercept) | MLB; PitchFX-based 2008-2016, Statcast 2017+ | Web CSV export, free | Governed by MLB terms (see Stats API row); CSV docs state no explicit volume limits | Proof of concept only; written MLBAM authorization needed for commercial use | Data subject to revision (pybaseball notes 700k+ pitches/season, subject to update). 2026 plate-location coordinate change (see below). Low effort |
| Savant Minor League Statcast Search | Same style of pitch data, filters include ABS Challenges | Triple-A all games from 2023 (PCL and Charlotte home 2022); Florida State League (Single-A) from 2021; "certain levels and ballparks" only; 2026 present (e.g., St. Lucie, Syracuse) | Web CSV, free | Same MLB terms | Same as above | Coverage limited to FSL for Single-A; most MiLB data non-public. Low effort |
| MLB Stats API / GUMBO | Schedules, rosters, box scores, play-by-play, standings | MLB and minors | REST, no official public docs found | Data subject to MLBAM copyright notice permitting individual, non-commercial, non-bulk use only; other use needs prior written MLBAM authorization | Not usable commercially without written authorization | Unofficial docs only. Moderate effort |
| pybaseball | Python wrapper for Savant, FanGraphs, Baseball Reference, plus Chadwick/Retrosheet/Lahman | Per wrapped source | pip, free | MIT, Copyright 2017 James LeDoux | Code usable; data governed by each upstream provider's terms | Releases may lag. Low effort |
| baseballr (R) | Wraps MLB Stats API, Savant incl. minors and WBC, ESPN, NCAA, Chadwick, Retrosheet etc. | Per source | CRAN/GitHub, free | MIT | Code usable; upstream data terms still apply | Actively maintained, nightly data workflows. Low effort |
| Retrosheet | Historical play-by-play/event files | Historical | Download, free | Free for any use including commercial; must prominently state "The information used here was obtained free of charge from and is copyrighted by Retrosheet." | Yes, with attribution | Historical only, not tracking data. Low effort |
| Chadwick Bureau Register | Player ID crosswalk | All | GitHub, free | Open Data Commons Attribution License | Yes, with attribution | Public extract updated roughly weekly. Low effort, essential for ID joins |
| TrackMan Baseball (own feeds) | CSV: RelSpeed, PlateLocSide, etc. | Club's own parks | Vendor software export, license from vendor | Proprietary; club's data rights come from its TrackMan contract (not read) | Yes under club's own contract | See schema findings below |
| Blast Motion | Bat sensor metrics | Club/player's own | App export to CSV/Excel, incl. team report; Blast Connect subscription | Vendor contract (not read) | Own data under contract | Export is manual per UI; no public API found |
| Rapsodo | Pitching/hitting reports | Own | Reports; CSV only on higher cloud subscription | Vendor contract (not read) | Own data under contract | Manual export |
| HitTrax | Batted-ball speed, launch angle, spray, zone | Own | Export details not found | Not read | Unknown | Gap |
| Hawk-Eye-derived bat tracking (Savant) | Swing speed/path from optical tracking | MLB: second half 2023 onward; swing length and contact metrics 2024; attack angle/direction/tilt added May 2025 | Via Savant | MLB terms | As Savant | Public minor-league bat tracking not found |
| Open-Meteo paid commercial plan | Weather | Global | Paid API with commercial licence | Free tier is non-commercial; dedicated commercial plans include a commercial use licence | Only on paid plan | Pricing not captured |

Supporting facts:
- MLB Stats API and MLB data terms: "permit only individual, non-commercial, and non-bulk use ... prohibiting any other form of use without prior written authorization from MLBAM" — secondary summary via search of the notice at gdx.mlb.com/components/copyright.txt (could not open directly); the MLB-StatsAPI README itself says "Use of MLB data is subject to the notice posted at http://gdx.mlb.com/components/copyright.txt." [MLB-StatsAPI repo](https://github.com/toddrob99/MLB-StatsAPI)
- Savant CSV docs: fields, no stated limits, and 2026 coordinate change: through 2025 plate position was measured at front of plate; from 2026 it aligns with ABS at middle of plate. [Savant CSV docs](https://baseballsavant.mlb.com/csv-docs)
- Minor league coverage as above. [Savant minors search](https://baseballsavant.mlb.com/statcast-search-minors)
- pybaseball wraps Savant, FanGraphs, Baseball Reference; license MIT. [repo](https://github.com/jldbc/pybaseball), [LICENSE](https://raw.githubusercontent.com/jldbc/pybaseball/master/LICENSE)
- baseballr MIT and wrapped sources. [repo](https://github.com/BillPetti/baseballr)
- Retrosheet notice (via search result of the notice page). [notice](https://www.retrosheet.org/notice.txt)
- Chadwick Register ODC-By. [repo](https://github.com/chadwickbureau/register)
- Blast export options. [Blast help](https://blast-motion.helpjuice.com/70968-troubleshooting-blast-connect/generating-a-team-report-export); Rapsodo CSV only with higher cloud subscription. [Rapsodo export guide](https://shotmetrics-ai.com/resources/rapsodo-csv-export/)
- Bat tracking timeline. [Baseball Egg](https://baseballegg.com/2026/09/08/the-numbers-hidden-inside-every-baseball-swing), [Savant leaderboard](https://baseballsavant.mlb.com/leaderboard/bat-tracking/swing-path-attack-angle)
- Open-Meteo free tier non-commercial; commercial plans licensed. [Open-Meteo terms](https://open-meteo.com/en/terms), [pricing](https://open-meteo.com/en/pricing)

### Omitted for license reasons
Count: 8 sources omitted because their license or terms restrict for-profit use, are share-alike/copyleft, or are unstated.

### Inferences
- The proof of concept can use Savant/Stats API for development, but operational use inside a club needs either written MLBAM authorization or data supplied through the club's MLB relationship. This conflicts with the instruction to list Savant and Stats API; I included them with this limit stated plainly.
- Pybaseball/baseballr MIT licensing covers only the code; scraping FanGraphs/Baseball Reference through them is not cleared by the MIT license.

### Gaps
- Could not open mlb.com terms of use, gdx.mlb.com notice, retrosheet.org (read only via search snippet), weather.gov NWS terms, arXiv.
- Savant CSV row cap and rate limits: not documented on pages read; widely cited 25,000-row cap not verified.
- TrackMan/Hawk-Eye field-level schema comparisons for the TrackMan-to-Hawk-Eye mapping, and published harmonization methods: not found beyond the items below.
- Hawk-Eye native export schema: no public documentation found.
- Park factors, umpire-zone datasets and their licenses: not verified.
- Open academic tracking datasets with explicit commercial-compatible licenses: none verified (the arXiv swing-tracking paper 2507.01238 could not be opened).
- HitTrax export format; Pitcher List and Baseball Prospectus terms (BP page found but not readable).

## TrackMan and Hawk-Eye schemas and comparisons

### Takeaway
TrackMan documents its CSV fields and coordinates publicly; Hawk-Eye documentation is not public. Published comparisons show systematic differences (extension) but no formal harmonization method was found.

### Cited Findings
- TrackMan pitching coordinate system: origin at back tip of home plate, x positive toward 3B, y positive toward pitcher, z up; RelSpeed in mph or km/h; PlateLocSide is distance from the plate center at the front of the plate, positive toward the right from pitcher's view. — [TrackMan Baseball support](https://support.trackmanbaseball.com/hc/en-us/articles/5089413493787-V3-FAQs-Radar-Measurement-Glossary-Of-Terms)
- TrackMan CSV request process. — [TrackMan CSV help](https://support.trackmanbaseball.com/hc/en-us/articles/32738741200411-CSV-How-To-Request-Receive-CSV-Files)
- Hawk-Eye replaced TrackMan in MLB in 2020; Hawk-Eye reported league-average extension about a third of a foot longer than TrackMan/PITCHf/x (about six feet). — [Baseball Cloud blog](https://baseballcloud.blog/2020/08/14/is-hawk-eye-inflating-extensions/)
- Savant lists 2026 plate-location convention change to middle-of-plate. — [Savant CSV docs](https://baseballsavant.mlb.com/csv-docs)
- ABS: Hawk-Eye in FSL from 2021, Triple-A select parks 2022, all Triple-A 2023, MLB challenge system 2026. — [MLB press release](https://www.mlb.com/press-release/press-release-mlb-announces-abs-challenge-system-coming-to-the-major-leagues-beginning-in-the-2026-season), [Wikipedia ABS](https://en.wikipedia.org/wiki/Automated_Ball-Strike_System)

### Inferences
- Because front-of-plate versus middle-of-plate conventions and extension offsets differ across systems and years, the engine needs a per-source, per-season coordinate adapter.

### Gaps
- Primary Hawk-Eye schema, TrackMan unit tables beyond these fields, and calibration papers.

## Omitted sources (count only)
8 omitted (see above).
